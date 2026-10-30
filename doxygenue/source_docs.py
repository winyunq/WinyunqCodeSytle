"""Source Doxygen comments only: XML discovery, verified local trivia splices.

This module never writes a function body, an external .dox or generated HTML.
Comment edits preserve the complete token AND preprocessor-directive streams.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET
from .cpp import SafeError, Source, lex, pairs, canonical, inside, sha, clean_comment, Token, HEADERS, EXTENSIONS
from .doxygen import Symbol, native_filesystem_path, xml_text


@dataclass
class Entity:
    name: str
    kind: str
    file: str
    line: int
    signature: str
    params: list[str]
    tparams: list[str]
    return_type: str
    protection: str
    args: str = ''
    refid: str = ''
    enum_parent: str = ''
    xml_documented: bool = False
    documentation: dict = field(default_factory=dict)
    documentation_counts: dict = field(default_factory=dict)

    def symbol(self, root):
        uid = sha((os.path.relpath(self.file, root) + '\0' + self.name + '\0' + self.kind + self.args).encode())[:20]
        return Symbol(uid, self.refid, self.name, self.kind, self.signature, self.args,
                      self.file, self.line, '', 0, 0, self.protection, '', '', '')


def inventory(catalog):
    catalog.ensure()
    from .views import documentation_from_xml, prose
    from collections import Counter
    def semantics(entity, node):
        import copy
        scoped = ET.Element('documentation')
        for tag in ('briefdescription','detaileddescription','inbodydescription'):
            value = node.find(tag)
            if value is not None: scoped.append(copy.deepcopy(value))
        entity.documentation = documentation_from_xml(scoped)
        counts = {}
        for pl in scoped.findall(".//parameterlist"):
            kind = pl.get("kind", "")
            names = [prose(n) for n in pl.findall("parameteritem/parameternamelist/parametername")]
            for name, count in Counter(names).items():
                counts[kind + ":" + name] = counts.get(kind + ":" + name, 0) + count
        entity.documentation_counts = counts
        return entity
    folder = Path(catalog.last_build['xml'])
    result = {}
    def path_of(loc):
        if loc is None or not loc.get('file'): return ''
        p = canonical(Path(catalog.root) / loc.get('file'))
        return p if p in catalog.hashes and Path(p).suffix.lower() in EXTENSIONS else ''
    def parameters(node, tag):
        result=[]
        for p in node.findall(tag):
            typ=xml_text(p.find('type')).strip()
            if typ in {'void','...'}:continue
            name=p.findtext('declname') or p.findtext('defname') or ''
            if not name and tag.startswith('templateparamlist'):
                m=re.search(r'\b(?:typename|class|int|unsigned|size_t|auto)\s+(\w+)\s*$',typ)
                if m:name=m.group(1)
            result.append(name)
        return result
    for entry in ET.parse(native_filesystem_path(folder / 'index.xml')).getroot().findall('compound'):
        ref = entry.get('refid', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', ref): raise SafeError('XML refid 越界。')
        tree = ET.parse(native_filesystem_path(folder / (ref + '.xml'))).getroot()
        for comp in tree.findall('compounddef'):
            ck = comp.get('kind', '')
            loc = comp.find('location'); path = path_of(loc)
            if ck in {'class','struct','union','namespace'} and path:
                name = comp.findtext('compoundname') or ''
                e = Entity(name, ck, path, int(loc.get('line', '0')), ck+' '+name,
                           [], parameters(comp, 'templateparamlist/param'), '', comp.get('prot','public'),
                           refid=comp.get('id',''), xml_documented=bool(xml_text(comp.find('briefdescription')) or xml_text(comp.find('detaileddescription'))))
                result[(e.name,e.kind,e.file,e.args)] = semantics(e, comp)
        for m in tree.findall('.//memberdef'):
            kind = m.get('kind','')
            if kind not in {'function','variable','property','typedef','enum'}: continue
            loc=m.find('location'); path=path_of(loc)
            if not path: continue
            name=m.findtext('qualifiedname') or m.findtext('name') or ''
            args=m.findtext('argsstring') or ''
            e=Entity(name,kind,path,int(loc.get('line','0')),
                (m.findtext('definition') or name)+args,parameters(m,'param'),parameters(m,'templateparamlist/param'),
                xml_text(m.find('type')),m.get('prot','public'),args,m.get('id',''),
                xml_documented=bool(xml_text(m.find('briefdescription')) or xml_text(m.find('detaileddescription'))))
            result[(e.name,e.kind,e.file,e.args)]=semantics(e, m)
            if kind=='enum':
                for v in m.findall('enumvalue'):
                    leaf=v.findtext('name') or ''
                    ve=Entity(name+'::'+leaf,'enumvalue',path,e.line,leaf,[],[],'',e.protection,
                        refid=v.get('id',''),enum_parent=name,
                        xml_documented=bool(xml_text(v.find('briefdescription')) or xml_text(v.find('detaileddescription'))))
                    result[(ve.name,ve.kind,ve.file,'')]=semantics(ve, v)
    return sorted(result.values(),key=lambda e:(e.file,e.line,e.name,e.args))


def resolve_entity(engine,name='',path=''):
    # A default remains a convenience; explicit name/path never require selection.
    if not name:
        s=engine._resolve_symbol('',path);name=s.name;path=path or s.file
    all_entities=inventory(engine.catalog)
    within=[e for e in all_entities if inside(e.file,engine.scope)]
    if path:
        p=canonical(Path(engine.root)/path)
        if not inside(p,engine.scope) or not Path(p).is_file():raise SafeError('注释 path 必须是 scope 内源码文件。')
        within=[e for e in within if e.file==p]
    full=(engine.container+'::'+name) if '::' not in name and engine.container else name
    matches=[e for e in within if e.name==full]
    if not matches:matches=[e for e in within if e.name==name]
    if not matches and '::' not in name:matches=[e for e in within if e.name.rsplit('::',1)[-1]==name]
    if len(matches)!=1:raise SafeError('源码注释对象未找到或存在重载；补充 name/path，不能猜测。')
    return matches[0]


def _source(catalog,path):
    raw=Path(path).read_bytes()
    if sha(raw)!=catalog.hashes.get(path):raise SafeError('源码相对 Doxygen 索引变化；重新索引后重试。')
    # Lexing is sufficient for comment-only changes, even for C++ templates.
    text=raw.decode('utf-8-sig');ts,cs,ds=lex(text)
    return Source(canonical(path),raw,text,raw.startswith(b'\xef\xbb\xbf'),ts,cs,ds)


def anchor(catalog,e):
    src=_source(catalog,e.file);ts=src.tokens
    starts=[0]+[m.end() for m in re.finditer('\n',src.text)]
    if not 1<=e.line<=len(starts):raise SafeError('Doxygen 行号失效。')
    begin=starts[e.line-1];end=starts[e.line] if e.line<len(starts) else len(src.text)
    leaf=e.name.rsplit('::',1)[-1].lstrip('~')
    candidates=[i for i,t in enumerate(ts) if begin<=t.start<end and t.value==leaf]
    if e.enum_parent:
        enum_i=next((i for i,t in enumerate(ts) if begin<=t.start<end and t.value=='enum'),None)
        if enum_i is None:raise SafeError('枚举源码行无法复核。')
        opening=next((i for i in range(enum_i,len(ts)) if ts[i].value=='{'),None)
        if opening is None:raise SafeError('枚举定义缺少左括号。')
        pm=pairs(ts);closing=pm[opening]
        candidates=[i for i in range(opening+1,closing) if ts[i].value==leaf]
    if len(candidates)!=1:raise SafeError('Doxygen 名称与原始源码行不能唯一对应。')
    i=candidates[0]
    # Prefer a conservative parser's complete declaration start when available.
    # Its unsafe-body flag does not make editing preceding comment bytes unsafe.
    try:
        parsed=Source.load(e.file,src.raw)
        occurrences=[o for o in parsed.occurrences if o.name==e.name and o.start<=ts[i].start<o.signature_end]
    except SafeError:occurrences=[]
    if len(occurrences)==1:
        at=occurrences[0].start
    else:
        at=ts[i].start if e.enum_parent else next(t.start for t in ts if begin<=t.start<end)
        if not e.enum_parent and src.text[begin:at].strip():raise SafeError('声明之前同一行有其他代码，拒绝注释插入。')
    # Include all preceding UE annotation calls, which Doxygen preprocesses away.
    macros={'UFUNCTION','UPROPERTY','UCLASS','USTRUCT','UENUM','UINTERFACE','UE_DEPRECATED','UE_NODISCARD'}
    pm=pairs(ts)
    while True:
        prev=[j for j,t in enumerate(ts) if t.end<=at]
        if not prev:break
        j=prev[-1]
        if ts[j].value!=')' or j not in pm:break
        op=pm[j];k=op-1
        if k<0 or ts[k].value not in macros:break
        if src.text[ts[j].end:at].strip():break
        at=ts[k].start
    # A whole-line comment can be inserted before an enumerator; inline entries
    # without an existing comment cannot safely gain a leading documentation block.
    if src.text[src.text.rfind('\n',0,at)+1:at].strip():
        raise SafeError('对象不是独立源码行，拒绝跨对象插入注释。')
    comments=[];stop=at
    for c in reversed(src.comments):
        if c.end>stop:continue
        gap=src.text[c.end:stop]
        if gap.strip() or gap.count('\n')>2 or '@file' in c.value:break
        prefix=src.text[src.text.rfind('\n',0,c.start)+1:c.start]
        if prefix.strip():break
        comments.append(c);stop=c.start
    return src,at,list(reversed(comments))


def format_doxygen(src,at,body):
    if not body.strip():raise SafeError('注释不能清空；请用独立 Delete。')
    if '/*' in body or '*/' in body or '\x00' in body or any(s.rstrip().endswith('\\') for s in body.splitlines()):
        raise SafeError('注释正文含边界或行拼接，拒绝写入。')
    allowed={'brief','details','param','tparam','return','returns','retval','note','warning','see','sa','ref','pre','post','since','deprecated','c','p','a','b','e','em','li','n','par','code','endcode'}
    if set(re.findall(r'[@\\]([A-Za-z]+)',body))-allowed:
        raise SafeError('源码文档含未允许的 Doxygen 指令；不能注入包含文件/外部命令。')
    indent=re.match(r'[ \t]*',src.text[src.text.rfind('\n',0,at)+1:at]).group()
    nl='\r\n' if '\r\n' in src.text else '\n'
    lines=body.strip().splitlines()
    # Align directive arguments and descriptions in a stable program-owned layout.
    parsed=[]
    for line in lines:
        m=re.match(r'^\s*(@(?:param(?:\[[^]]+\])?|tparam))\s+(\S+)\s+(.+)$',line)
        if m:parsed.append((m.group(1),m.group(2),m.group(3)))
        else:
            m=re.match(r'^\s*(@\w+)\s+(.+)$',line)
            parsed.append((m.group(1),'',m.group(2)) if m else ('','',line.strip()))
    command_width=max([len(x[0]) for x in parsed]+[6])+1
    name_width=max([len(x[1]) for x in parsed]+[0])+1
    out=[]
    for cmd,name,text in parsed:
        if name:out.append(cmd.ljust(command_width)+name.ljust(name_width)+text)
        elif cmd:out.append(cmd.ljust(command_width)+text)
        else:out.append(text)
    return '/**'+nl+nl.join(indent+' *'+(' '+line if line else '') for line in out)+nl+indent+' */'


def source_comment(engine,name='',path='',action='preview',old_code='',new_code='',operation='modify'):
    e=resolve_entity(engine,name,path);src,at,cs=anchor(engine.catalog,e)
    before='\n'.join(clean_comment(c.value) for c in cs)
    locator={'name':e.name,'path':os.path.relpath(e.file,engine.root)}
    if action=='prepare':
        return {'target':locator,'kind':'comment','part':'declaration','text':before,
                'comments':[{'text':before,'kind':'leading_group'}] if cs else [],
                'source_hash':src.revision,'locked':engine._locked(e.symbol(engine.root)),
                'location_line':src.text.count('\n',0,at)+1}
    if operation=='add' and cs:raise SafeError('已有声明前注释；使用 modify，不能叠加重复文档。')
    if before!=old_code:raise SafeError('声明前注释在准备后已变化；重新 prepare，不自动丢弃旧注释。')
    start,end=(cs[0].start,cs[-1].end) if cs else (at,at)
    replacement=format_doxygen(src,start,new_code)
    if not cs:
        nl='\r\n' if '\r\n' in src.text else '\n'
        indent=re.match(r'[ \t]*',src.text[src.text.rfind('\n',0,at)+1:at]).group()
        replacement+=nl+indent
    text=src.text[:start]+replacement+src.text[end:]
    new_tokens,new_comments,new_dirs=lex(text)
    if [t.value for t in src.tokens]!=[t.value for t in new_tokens] or [d.value for d in src.directives]!=[d.value for d in new_dirs]:
        raise SafeError('注释编辑改变了代码或预处理指令。')
    delta=len(replacement)-(end-start)
    # Exact preservation of every unrelated comment (including inline comments).
    old_out=[(c.value,c.start,c.end) for c in src.comments if c.end<=start or c.start>=end]
    new_out=[(c.value,c.start if c.end<=start else c.start-delta,c.end if c.end<=start else c.end-delta)
             for c in new_comments if c.end<=start or c.start>=start+len(replacement)]
    if old_out!=new_out:raise SafeError('注释编辑影响了其他注释。')
    symbol=e.symbol(engine.root)
    plan=engine._plan('Write','comment',symbol,[(src.path,src.raw,src.encode(text))],{src.path:src.raw},
                      {src.path:(src.text[start:end],replacement)})
    plan.update({'source_comments_only':True,'code_tokens_unchanged':True,'directives_unchanged':True})
    return plan


def update_fields(engine, name, path, fields):
    """Patch named documentation fields; omitted fields stay on disk, not in AI context.

    Normal Doxygen blocks have one directive per line (the program's formatter).
    Ambiguous compact/implicit blocks retain their prose as details rather than
    being discarded. This is an additive/modify API, never field deletion.
    """
    permitted={'brief','details','params','tparams','returns','note','warning'}
    if not isinstance(fields,dict) or not fields or set(fields)-permitted:
        raise SafeError('fields 仅允许 brief/details/params/tparams/returns/note/warning。')
    e=resolve_entity(engine,name,path)
    src,at,comments=anchor(engine.catalog,e)
    body='\n'.join(clean_comment(c.value) for c in comments)
    before=body
    # Compact multi-directive lines cannot be split without reinterpreting prose.
    # Reject instead of silently swallowing an omitted param/return field.
    for line in body.splitlines():
        if len(re.findall(r'[@\\](?:brief|details|param|tparam|returns?|note|warning|par|pre|post)\b',line))>1:
            raise SafeError('多个注释字段共用一行，部分字段编辑无法安全分界；请使用完整注释预览。')
    changes=[]
    for key,value in fields.items():
        if key in {'params','tparams'}:
            if not isinstance(value,dict) or not value:raise SafeError('params/tparams 是非空名称到说明的对象。')
            known=e.params if key=='params' else e.tparams
            for param,desc in value.items():
                if param not in known:raise SafeError('参数名不在当前声明中：'+str(param))
                changes.append(('param' if key=='params' else 'tparam',param,desc))
        else:changes.append(('return' if key=='returns' else key,'',value))
    for command,param,value in changes:
        if not isinstance(value,str) or not value.strip() or len(value)>16000:
            raise SafeError('文档字段必须为非空说明；删除需要独立 Delete。')
        if re.search(r'[@\\](?:brief|details|param|tparam|return|returns|note|warning)\b',value):
            raise SafeError('字段值只写说明，不再嵌套 Doxygen 字段标记。')
        pattern=r'(?m)^[ \t]*[@\\]'+('returns?' if command=='return' else command)
        if param:pattern+=r'(?:\[[^\]]+\])?\s+'+re.escape(param)+r'(?=\s|$)'
        else:pattern+=r'\b'
        hits=list(re.finditer(pattern,body))
        if len(hits)>1:raise SafeError('同一注释字段出现多次；请先显式读取、核对完整注释。')
        entry='@'+command+(' '+param if param else '')+' '+value.strip()
        if hits:
            a=hits[0].start();rest=body[hits[0].end():]
            if param:
                direction=re.search(r'\[([^\]]+)\]',hits[0].group())
                if direction:entry='@'+command+'['+direction.group(1)+'] '+param+' '+value.strip()
            next_command=re.search(r'(?m)^[ \t]*[@\\][A-Za-z]\w*\b',rest)
            b=hits[0].end()+next_command.start() if next_command else len(body)
            # A blank paragraph ends brief; following prose belongs to details.
            if command=='brief':
                blank=re.search(r'\n[ \t]*\n',body[hits[0].end():b])
                if blank:b=hits[0].end()+blank.start()
            body=body[:a]+entry+'\n'+body[b:].lstrip('\n')
        else:
            # Keep any previously untagged prose, don't replace it by a summary.
            body=body.rstrip()+('\n' if body.strip() else '')+entry
    return source_comment(engine,name,path,'preview',before,body,'modify')
