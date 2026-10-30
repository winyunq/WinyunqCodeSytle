"""Real newline-delimited stdio JSON-RPC. Four tools; a single representation per result."""
from __future__ import annotations
import json
import sys
import time
import traceback
from .common import SafeError,encode,json_load
from . import __version__


def S(description='',enum=None):
    r={'type':'string'}
    if description:r['description']=description
    if enum:r['enum']=enum
    return r

def schema(properties):return {'type':'object','properties':properties,'additionalProperties':False}
LOCATION={'name':S('本次对象名称；省略用Target，不是强制参数。'),'path':S('本次精确路径，不能越过项目。')}
SCHEMAS={
 'Read':schema({**LOCATION,'query':S('找已有能力或数据入口。'),'kind':S(enum=['code','data','asset']),
    'view':S('可一次读足，不需要逐层打卡。',['auto','brief','overview','details','documentation','code','raw','comments','rows','project','uses','changes','history','inventory','plan']),
    'limit':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0},
    'fields':{'type':'array','items':S()},'where':{'type':'object'},'select':{'type':'boolean'},
    'part':S(enum=['body','declaration','definition','file_header']),
    'base':S(),'target':S('diff目标，例如WORKTREE/INDEX/PLAN。'),'detail':{'type':'boolean'}}),
 'Write':schema({**LOCATION,'action':S(enum=['preview','apply']),'plan':S('预览计划，不是对象ID。'),
    'kind':S(enum=['code','comment','data','asset','function','include']),
    'old_code':S(),'new_code':S('modify_member 使用完整成员声明，并且只改变前置 UPROPERTY/UFUNCTION。'),'operation':S('modify_member 需同时提供完整 name 和精确 header path。JSON 坦克替换仅用于配置批准的文件。',['modify','add','add_symbol','add_member','modify_member','modify_members','modify_local_initializers','modify_smoke_tank_target','replace_tank_asset_paths','replace_focus_tank_paths','replace_focus_tank_description','function','include']),
    'members':{'type':'array','items':{'type':'object','properties':{'name':S('目标类型内的字段名，可用完整限定名。'),'old_code':S('当前完整字段声明。'),'new_code':S('添加或更新 UPROPERTY(...) 后的完整字段声明。')},'additionalProperties':False},'description':'modify_members 一次预览同一类型中的多个字段标记；顶层 name/path 是其中一个现存字段的精确定位。'},
    'part':S(enum=['body','declaration','definition','file_header']),
    'fields':{'type':'object','description':'只改某个Doxygen字段，未给字段保留。'},
    'rows':{'type':'array','items':{'type':'object'},'description':'按既有主键增改，不删除省略的记录/字段。'},
    'import_file':S('项目内JSON/CSV文件；程序批量读取，不让模型抄全部数据。'),
    'mapping':{'type':'object','additionalProperties':S(),'description':'目标字段:源字段，一次定义导入映射。'},
    'includes':{'type':'array','items':S()},'placement':S(enum=['before','after']),'comment_id':S()}),
 'Delete':schema({**LOCATION,'action':S(enum=['preview','apply']),'plan':S(),'kind':S(enum=['data','asset','code','symbol','comment','include']),
    'keys':{'type':'array','items':{'type':['string','integer']}},'old_code':S(),
    'part':S(enum=['body','declaration','definition','file_header']),'comment_id':S(),'reason':S('删除理由，不是批准凭证。')}),
  'Configure':schema({**LOCATION,'action':S(enum=['status','target','parent','child','scope','abort','lock','lock_status','validate','check_localization','check_comments','export_docs','generate_website','reindex','approvals','policy']),
    'kind':S(enum=['data','asset','code']),'reason':S(),'output_format':S(enum=['html','latex','pdf']),'limit':{'type':'integer','minimum':1,'maximum':100},
    'audience':S('网页文档受众；用户文档只取配置的公开头文件。',['user','developer','both']),
    'languages':{'type':'array','items':S('语言代码，如 en、zh-CN。')}})
}
DESCRIPTIONS={
 'Read':'发现已有工程能力与数据；默认一个brief，直接选overview/details/rows即可一次读足。Target仅补缺省。',
 'Write':'增加/编辑既有记录、源码或注释，保留省略内容。preview→apply。modify_member 可给单个字段/函数增改 UPROPERTY/UFUNCTION；modify_members 可在一个事务中修改同一类型的多个字段标记，并校验 C++ 成员签名不变。Config 只用于需要配置读写的字段。',
 'Delete':'独立删除：preview→本机用户审批具体差异→apply。理由文字不是批准。不接受通过Write删除。',
  'Configure':'缺省Target、范围、锁、文档检查/导出、验证。generate_website 按项目配置生成开发者与用户网页，保留翻译命中记录。check_localization 只读检查原生 UE manifest/archive，name 为本地化目标（默认 Game），path 可指定项目内 manifest。不能自行改变维护权限、批准删除、解锁或执行任意命令。'}

def validate(v,rule,at='arguments'):
    ty=rule.get('type');types={'string':str,'integer':int,'number':(int,float),'boolean':bool,'object':dict,'array':list}
    if isinstance(ty,list):ok=any(type(v) is types[t] for t in ty)
    elif ty=='number':ok=type(v) in (int,float)
    else:ok=type(v) is types[ty]
    if not ok:raise SafeError(at+' 类型错误。')
    if 'enum'in rule and v not in rule['enum']:raise SafeError(at+' 值不支持。')
    text_limit=1048576 if at in ('arguments.old_code','arguments.new_code') else 32000
    if isinstance(v,str) and len(v)>text_limit:raise SafeError(at+' 文本过长。')
    if type(v) is int and (v<rule.get('minimum',-10**18) or v>rule.get('maximum',10**18)):raise SafeError(at+' 超出范围。')
    if isinstance(v,list):
        if len(v)>1000:raise SafeError('内联最多1000项，更大批次使用import_file。')
        for i,x in enumerate(v):validate(x,rule.get('items',{'type':'object'}),at+f'[{i}]')
    if isinstance(v,dict):
        props=rule.get('properties',{})
        if rule.get('additionalProperties') is False and set(v)-props.keys():raise SafeError(at+' 未知字段：'+','.join(set(v)-props.keys()))
        for k,x in v.items():
            if k in props:validate(x,props[k],at+'.'+k)
            elif isinstance(rule.get('additionalProperties'),dict):validate(x,rule['additionalProperties'],at+'.'+k)

class Server:
    def __init__(self,engine,mode='structured'):
        self.engine=engine;self.mode=mode;self.initialized=False;self.client='unknown';self.version='2025-11-25'
    @staticmethod
    def error(id,code,message):return {'jsonrpc':'2.0','id':id,'error':{'code':code,'message':message}}
    def process(self,r):
        if not isinstance(r,dict) or r.get('jsonrpc')!='2.0' or not isinstance(r.get('method'),str):return self.error(None,-32600,'Invalid request')
        if 'id' not in r:return None
        id=r['id'];p=r.get('params',{});m=r['method']
        if type(id) not in (int,str) or not isinstance(p,dict):return self.error(None,-32600,'Invalid request')
        def out(value):return {'jsonrpc':'2.0','id':id,'result':value}
        if m=='initialize':
            ci=p.get('clientInfo',{})
            if not isinstance(ci,dict):return self.error(id,-32602,'clientInfo must be object')
            self.initialized=True;self.client=str(ci.get('name','unknown'))
            requested=p.get('protocolVersion');self.version=requested if requested in ('2025-11-25','2025-06-18','2025-03-26','2024-11-05') else '2025-11-25'
            return out({'protocolVersion':self.version,'capabilities':{'tools':{'listChanged':False}},
                        'serverInfo':{'name':'UnrealEngineCPPCodingMCP','version':__version__},
                        'instructions':'Use the ue-maintenance skill. Data/config before new runtime code when existing project data already expresses the request. Reuse existing APIs; add a capability inside its owner only for a demonstrated gap. No forced read ladder. Read directly; Write preview/apply; Delete also needs local approval. Do not route unsupported data edits into C++. Task permissions are user configured, not model claims. Output is single structuredContent; text mode is available for older clients.'})
        if m=='ping':return out({})
        if not self.initialized:return self.error(id,-32002,'Initialize first')
        if m=='tools/list':return out({'tools':[{'name':n,'description':DESCRIPTIONS[n],'inputSchema':s,**({'outputSchema':{'type':'object'}} if self.mode=='structured' and self.version not in ('2024-11-05','2025-03-26') else {}),'annotations':{'readOnlyHint':n=='Read','destructiveHint':n!='Read','openWorldHint':False}} for n,s in SCHEMAS.items()]})
        if m!='tools/call':return self.error(id,-32601,'Unknown method')
        name=p.get('name');args=p.get('arguments',{})
        if not isinstance(name,str) or name not in SCHEMAS:return self.error(id,-32602,'Unknown tool')
        try:
            validate(args,SCHEMAS[name]);result=getattr(self.engine,name.lower())(**args)
            if self.mode=='text' or self.version in ('2025-03-26','2024-11-05'):
                return out({'content':[{'type':'text','text':encode(result)}]})
            return out({'content':[],'structuredContent':result})
        except (SafeError,OSError,UnicodeError,ValueError) as e:
            return out({'isError':True,'content':[{'type':'text','text':str(e)}]})
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return out({'isError':True,'content':[{'type':'text','text':'内部错误；检查stderr/事务日志，不回退整文件。'}]})
    def exchange(self,line):
        start=time.perf_counter()
        try:r=json_load(line);response=self.process(r)
        except (ValueError,SafeError):r={};response=self.error(None,-32700,'Invalid JSON')
        wire=encode(response) if response is not None else ''
        method=r.get('method','invalid') if isinstance(r,dict) else 'invalid'
        try:self.engine.store.audit(self.engine.root,self.engine.session,self.client,line,wire,(time.perf_counter()-start)*1000,method)
        except Exception:traceback.print_exc(file=sys.stderr)
        return wire
    def run(self):
        while True:
            line=sys.stdin.buffer.readline(1024*1024+1)
            if not line:break
            if len(line)>1024*1024:break
            try:response=self.exchange(line.decode('utf-8-sig'))
            except UnicodeError:response=encode(self.error(None,-32700,'Invalid UTF8'))
            if response:sys.stdout.buffer.write((response+'\n').encode('utf-8'));sys.stdout.buffer.flush()
