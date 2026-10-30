"""Deterministic row upsert. Omitted rows/fields survive; deletion is separate."""
from __future__ import annotations
import copy
import csv
import io
import math
import re
from .common import *

def identity(value,binding):
    if type(value) not in (str,int) or (isinstance(value,str) and not value.strip()):raise SafeError('主键必须是非空字符串或整数。')
    return (type(value).__name__,value.casefold() if isinstance(value,str) and binding.get('case_insensitive_key',binding.get('format')=='ue_datatable') else value)

def index(rows,binding):
    if not isinstance(rows,list) or len(rows)>100000:raise SafeError('数据必须是最多100000条记录的数组。')
    result={};key=binding['key']
    for row in rows:
        if not isinstance(row,dict) or key not in row:raise SafeError('每条记录需要主键 '+key)
        i=identity(row[key],binding)
        if i in result:raise SafeError('重复主键：'+str(row[key]))
        result[i]=row
    return result

def check_row(row,binding,partial=False):
    if set(row)-binding['fields'].keys():raise SafeError('未知字段：'+', '.join(sorted(set(row)-binding['fields'].keys())))
    if not partial:
        missing=set(binding.get('required',binding['fields'].keys()))-row.keys()
        if missing:raise SafeError('缺少字段：'+', '.join(sorted(missing)))
    expected={'string':str,'integer':int,'number':(int,float),'boolean':bool,'object':dict,'array':list}
    for n,v in row.items():
        rule=binding['fields'][n]
        if v is None and rule.get('nullable'):continue
        t=rule['type']
        if t=='number':valid=type(v) in (int,float) and math.isfinite(v)
        else:valid=type(v) is expected[t]
        if not valid:raise SafeError(f'{n} 类型错误，需要 {t}，不自动猜值。')
        if 'enum'in rule and v not in rule['enum']:raise SafeError(n+' 不在枚举范围。')
        if t in ('number','integer'):
            if 'minimum'in rule and v<rule['minimum']:raise SafeError(n+' 小于下限。')
            if 'maximum'in rule and v>rule['maximum']:raise SafeError(n+' 大于上限。')

def merge_object(old,new):
    result=copy.deepcopy(old)
    for k,v in new.items():
        result[k]=merge_object(result[k],v) if isinstance(result.get(k),dict) and isinstance(v,dict) else copy.deepcopy(v)
    return result

def merge(rows,updates,binding):
    original=index(rows,binding);index(updates,binding)
    out=copy.deepcopy(rows);positions={identity(r[binding['key']],binding):i for i,r in enumerate(out)}
    changes=[]
    for update in updates:
        check_row(update,binding,True);key=identity(update[binding['key']],binding)
        old=original.get(key)
        new=merge_object(old,update) if old is not None else copy.deepcopy(update)
        if old is not None:new[binding['key']]=old[binding['key']] # FName case does not rename a row.
        check_row(new,binding)
        if new==old:continue
        changes.append({'key':new[binding['key']],'change':'add' if old is None else 'edit',
                        'fields':{k:{'before':None if old is None else old.get(k),'after':v} for k,v in new.items() if old is None or k not in old or v!=old[k]}})
        if old is None:out.append(new)
        else:out[positions[key]]=new
    return out,changes

def remove(rows,keys,binding):
    if not isinstance(keys,list) or not keys:raise SafeError('Delete 需要明确的非空 keys。')
    selected=[identity(k,binding) for k in keys]
    if len(set(selected))!=len(selected):raise SafeError('删除键重复。')
    source=index(rows,binding)
    if any(k not in source for k in selected):raise SafeError('删除键不存在，不猜测相近项。')
    return [r for k,r in source.items() if k not in selected],[{'key':source[k][binding['key']],'change':'delete','before':source[k]} for k in selected]

def csv_value(v,rule):
    t=rule['type']
    if t=='string':return v
    if t=='integer' and re.fullmatch(r'-?(?:0|[1-9]\d*)',v):return int(v)
    if t=='number':
        try:return float(v)
        except ValueError:pass
    if t=='boolean' and v in ('true','false'):return v=='true'
    if t in ('object','array'):
        try:return json_load(v)
        except ValueError:pass
    raise SafeError('CSV 字段类型转换失败：'+str(v)[:80])

def load(raw,format,binding=None):
    text=raw.decode('utf-8-sig')
    if format=='json':
        rows=json_load(text)
    elif format=='csv':
        reader=csv.DictReader(io.StringIO(text,newline=''))
        fields=reader.fieldnames or []
        if not fields or len(set(fields))!=len(fields):raise SafeError('CSV 表头为空或重复。')
        rows=[]
        for row in reader:
            if None in row or None in row.values():raise SafeError('CSV 列数量不匹配。')
            if binding:
                if set(row)-binding['fields'].keys():raise SafeError('CSV 包含未声明列。')
                row={k:csv_value(v,binding['fields'][k]) for k,v in row.items()}
            rows.append(row)
    else:raise SafeError('导入仅支持标准 JSON 数组或 CSV；没有伪造星际地图格式解析器。')
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise SafeError('需要记录数组，不接受整工程或任意对象覆盖。')
    if binding:index(rows,binding)
    return rows

def _spans(text):
    decoder=json.JSONDecoder();i=0
    while i<len(text) and text[i].isspace():i+=1
    if i>=len(text) or text[i]!='[':raise SafeError('JSON 数据源须为顶层记录数组。')
    i+=1;out=[]
    while True:
        while i<len(text) and (text[i].isspace() or text[i]==','):i+=1
        if i>=len(text):raise SafeError('JSON 数组未闭合。')
        if text[i]==']':return out,i
        obj,end=decoder.raw_decode(text,i);out.append((i,end,obj));i=end

def render(oldraw,rows,binding):
    """Unchanged JSON row bytes survive. Edited rows are formatted by the program.
    CSV is serialized as CSV (never treated as a spreadsheet); dialect/newline/BOM are retained.
    """
    fmt=binding.get('format','json');bom=b'\xef\xbb\xbf' if oldraw.startswith(b'\xef\xbb\xbf') else b''
    text=oldraw.decode('utf-8-sig');nl='\r\n' if '\r\n' in text else '\n'
    if fmt=='csv':
        reader=csv.reader(io.StringIO(text,newline=''));fields=next(reader)
        for row in rows:
            for k in row:
                if k not in fields:fields.append(k)
        stream=io.StringIO(newline='');w=csv.DictWriter(stream,fields,lineterminator=nl);w.writeheader()
        for row in rows:
            def val(v):
                if type(v) in (bool,dict,list) or v is None:return encode(v)
                return v
            w.writerow({k:val(v) for k,v in row.items()})
        return bom+stream.getvalue().encode('utf-8')
    spans,closing=_spans(text);old={identity(v[binding['key']],binding):(a,b,v) for a,b,v in spans}
    if load(oldraw,'json',binding)==rows:return oldraw
    multiline='\n' in text
    prefix='  '
    if spans:
        a=spans[0][0];candidate=text[text.rfind('\n',0,a)+1:a]
        if not candidate.strip():prefix=candidate
    pieces=[]
    for row in rows:
        match=old.get(identity(row[binding['key']],binding))
        if match and match[2]==row:piece=text[match[0]:match[1]]
        else:
            # Compact rows retain readable keys and values; do not rewrite neighboring rows.
            piece=json.dumps(row,ensure_ascii=False,allow_nan=False,separators=(', ',': '))
        pieces.append(piece)
    if not spans:
        left=text[:text.index('[')+1];right=text[closing:]
    else:left=text[:spans[0][0]];right=text[spans[-1][1]:];right=right[right.find(']'):]
    if multiline:
        if not left.endswith(prefix):left=left.rstrip()+nl+prefix
        separator=','+nl+prefix
        result=left+separator.join(pieces)+nl+right
    else:result=left+', '.join(pieces)+right
    # Semantic round-trip is mandatory before touching the original.
    raw=bom+result.encode('utf-8')
    if load(raw,'json',binding)!=rows:raise SafeError('JSON 写回核对失败。')
    return raw

def import_rows(root,relative,mapping,binding):
    p=path_in(root,relative);fmt=p.suffix.lower().lstrip('.')
    raw=read_bytes(p);rows=load(raw,fmt)
    if not isinstance(mapping,dict) or not mapping or any(not isinstance(k,str) or not isinstance(v,str) for k,v in mapping.items()):raise SafeError('导入需一次声明 目标字段:源字段 的 mapping。')
    if set(mapping)-binding['fields'].keys():raise SafeError('映射目标包含未知字段。')
    result=[]
    for i,row in enumerate(rows):
        if set(mapping.values())-row.keys():raise SafeError(f'第{i+1}条源记录缺少映射字段。')
        dest={k:(csv_value(row[v],binding['fields'][k]) if fmt=='csv' else row[v]) for k,v in mapping.items()}
        result.append(dest)
    return result,p,raw


def compact_changes(changes,limit=20,budget=12000):
    """Bound the model preview, never the actual plan or GUI approval record."""
    def short(value):
        if len(encode(value))<=300:return value
        return {'excerpt':encode(value)[:260],'omitted_chars':max(0,len(encode(value))-260)}
    result=[];used=0;trimmed=False
    for change in changes[:limit]:
        row={k:(v if k in ('key','change') else ({f:{q:short(z) for q,z in a.items()} for f,a in v.items()} if k=='fields' else short(v))) for k,v in change.items()}
        if len(encode(row))>4000:
            row={'key':short(change['key']),'change':change['change'],'details':'see local plan'}
        size=len(encode(row))
        if used+size>budget:trimmed=True;break
        trimmed=trimmed or row!=change
        result.append(row);used+=size
    return result,trimmed or len(result)<len(changes)
