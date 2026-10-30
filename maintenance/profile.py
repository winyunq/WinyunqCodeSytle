"""Startup-authorized capabilities. MCP cannot change them or execute arbitrary commands."""
from __future__ import annotations
import fnmatch
import json
from pathlib import Path
from .common import *

class Profile:
    def __init__(self,root,path=''):
        self.root=canonical(root); self.path=Path(path).resolve() if path else None
        self.raw=self.path.read_bytes() if self.path else b''
        self.data=json_load(self.raw.decode('utf-8-sig')) if self.raw else {}
        allowed={'version','label','mode','code_paths','data','aliases','forbid_added_tokens','validation','require_validation','pinned_files','json_path_patch','ini_tank_protocol_prune'}
        if not isinstance(self.data,dict) or set(self.data)-allowed: raise SafeError('维护配置含未知字段。')
        if self.data.get('version',1)!=1: raise SafeError('配置版本不支持。')
        self.mode=self.data.get('mode','read_only')
        if self.mode not in {'read_only','content','maintain'}: raise SafeError('mode 为 read_only/content/maintain。')
        for key in ('code_paths','forbid_added_tokens','pinned_files'):
            v=self.data.get(key,[])
            if not isinstance(v,list) or any(not isinstance(x,str) or not x.strip() for x in v): raise SafeError(key+' 应为字符串数组。')
        json_paths=self.data.get('json_path_patch',[])
        if not isinstance(json_paths,list) or len(json_paths)>16:
            raise SafeError('json_path_patch 必须是有界文件清单。')
        for path in json_paths:
            if not isinstance(path,str) or not path.endswith('.json') or Path(path).is_absolute() or '..' in Path(path).parts:
                raise SafeError('json_path_patch 只接受项目内明确 JSON 文件。')
            path_in(root,path)
        ini_paths=self.data.get('ini_tank_protocol_prune',[])
        if not isinstance(ini_paths,list) or len(ini_paths)>4:
            raise SafeError('ini_tank_protocol_prune 必须是有界文件清单。')
        for path in ini_paths:
            if not isinstance(path,str) or not path.endswith('.ini') or Path(path).is_absolute() or '..' in Path(path).parts:
                raise SafeError('ini_tank_protocol_prune 只接受项目内明确 INI 文件。')
            path_in(root,path)
        aliases=self.data.get('aliases',{})
        if not isinstance(aliases,dict) or any(not isinstance(k,str) or not isinstance(v,list) or any(not isinstance(x,str) for x in v) for k,v in aliases.items()):raise SafeError('aliases 为 词:同义词数组。')
        if not isinstance(self.data.get('data',[]),list):raise SafeError('data 必须为数组。')
        self.bindings={}
        for item in self.data.get('data',[]):
            valid={'name','path','format','key','brief','fields','required','references','consumers','case_insensitive_key'}
            if not isinstance(item,dict) or set(item)-valid or not {'name','path','key','fields'}<=item.keys(): raise SafeError('数据绑定必须声明 name/path/key/fields。')
            if item.get('format','json') not in ('json','csv','ue_datatable'): raise SafeError('数据写入支持 json/csv/ue_datatable。其他类型只列出，不改写。')
            if item['name'] in self.bindings or not isinstance(item['name'],str) or not item['name']: raise SafeError('数据名称必须唯一。')
            if not isinstance(item['fields'],dict) or item['key'] not in item['fields']: raise SafeError('主键必须包含在字段结构中。')
            for n,rule in item['fields'].items():
                if not isinstance(n,str) or not isinstance(rule,dict) or set(rule)-{'type','minimum','maximum','enum','description','nullable'}: raise SafeError('字段规则无效。')
                if rule.get('type') not in ('string','integer','number','boolean','object','array'): raise SafeError('字段类型无效。')
            if set(item.get('required',[]))-item['fields'].keys():raise SafeError('required 包含未知字段。')
            if item.get('format')=='ue_datatable':
                if not item['path'].startswith('/Game/') or '..' in item['path'] or item['key']!='Name': raise SafeError('编辑器适配仅支持 /Game/ 下既有 DataTable，主键 Name。')
            else:
                target=path_in(root,item['path'])
                if target.suffix.lower()!='.'+item.get('format','json'):raise SafeError('数据文件后缀必须与声明格式一致，不能把源码伪装成数据。')
            self.bindings[item['name']]=item
        for b in self.bindings.values():
            for field,other in b.get('references',{}).items():
                if field not in b['fields'] or other not in self.bindings:raise SafeError('引用规则指向未知字段/表。')
        self.pins={canonical(path_in(root,p)):sha(read_bytes(path_in(root,p))) for p in self.data.get('pinned_files',[])}
        self.fingerprint=digest({'raw':sha(self.raw),'pins':self.pins,'root':self.root})

    def assert_current(self):
        if self.path and self.path.read_bytes()!=self.raw: raise SafeError('用户配置已变化；重新连接，旧计划作废。')
        for path,value in self.pins.items():
            if not Path(path).is_file() or sha(read_bytes(path))!=value: raise SafeError('受信测试/约定文件变化：'+str(Path(path).relative_to(self.root)))

    def authorize(self,kind,paths=()):
        self.assert_current()
        if self.mode=='read_only': raise SafeError('当前只读。由用户在 GUI 选择维护配置，不存在 MCP 自行授权。')
        if kind in ('data','asset'):return
        if self.mode!='maintain': raise SafeError('本次为内容维护：不允许修改运行代码。先使用已有数据入口；不能绕到 C++。')
        for p in paths:
            rel=str(Path(p).relative_to(self.root)).replace('\\','/')
            if not any(fnmatch.fnmatch(rel,g) for g in self.data.get('code_paths',[])):raise SafeError('不在用户批准的代码范围：'+rel)
            if canonical(p) in self.pins:raise SafeError('不能修改本次受信测试。')

    def authorize_json_path_patch(self,path):
        self.authorize('data')
        target=canonical(path_in(self.root,path))
        approved={canonical(path_in(self.root,item)) for item in self.data.get('json_path_patch',[])}
        if target not in approved or target in self.pins:
            raise SafeError('JSON 路径未在当前维护配置中明确授权。')
        return target

    def authorize_ini_tank_protocol_prune(self,path):
        self.authorize('data')
        target=canonical(path_in(self.root,path))
        approved={canonical(path_in(self.root,item)) for item in self.data.get('ini_tank_protocol_prune',[])}
        if target not in approved or target in self.pins:
            raise SafeError('INI 坦克协议文件未在当前维护配置中明确授权。')
        return target

    def find_binding(self,name='',path=''):
        found=[b for b in self.bindings.values() if (not name or b['name']==name) and (not path or b['path']==path)]
        if len(found)!=1: raise SafeError('数据入口未绑定或不唯一；用户配置已有表及字段，MCP不新造数据系统。')
        return found[0]
