"""One maintenance entry: existing data and code are first-class, without parallel runtime systems."""
from __future__ import annotations
import copy
import collections
import difflib
import json
import re
from pathlib import Path
from doxygenue.engine import Engine as CodeEngine
from doxygenue.transactions import Plan
from doxygenue.views import compact_result
from doxygenue.cpp import lex
from .common import *
from .profile import Profile
from . import records, project

class Engine:
    def __init__(self,root,store,profile='',doxygen=''):
        self.root=canonical(root);self.store=store
        self.profile=Profile(root,profile)
        self.code=CodeEngine(root,store,doxygen)
        self.session=self.code.session
        self.target=None; self.parent=''; self.remembered={}
        self.pending=None;self.plan_profile='';self.plan_summary=None
        self.bridge=None
        validation=copy.deepcopy(self.profile.data.get('validation'))
        if validation:
            validation['commands']=[[a.replace('{package}',str(Path(__file__).resolve().parents[1])) for a in c] for c in validation['commands']]
            from doxygenue.validation import Validator
            from doxygenue.doxygen import dump_atomic
            p=store.path.parent/'validation_profiles'/ (self.profile.fingerprint+'.json')
            dump_atomic(p,validation)
            self.code.validator=Validator(p,store.path.parent/'validation')
        self.code.catalog.settings['aliases'].update(self.profile.data.get('aliases',{}))

    def abort(self):
        self.pending=None;self.plan_summary=None
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='asset_approvals'").fetchone():
            self.store.db.execute("UPDATE asset_approvals SET status='cancelled' WHERE root=? AND session=? AND status IN ('pending','approved')",(self.root,self.session))
        return self.code.abort()

    def _binding(self,name='',path=''):
        if not name and not path and self.target and self.target['kind']=='data':name=self.target['name']
        return self.profile.find_binding(name,path)

    def _domain(self,name='',path='',kind=''):
        if kind in {'data','asset'}:return 'data'
        if kind:return 'code'
        if name in self.profile.bindings or any(b['path']==path for b in self.profile.bindings.values() if path):return 'data'
        if not name and not path and self.target:return self.target['kind']
        return 'code'

    def _snapshot(self,b):
        if b.get('format')=='ue_datatable':
            from .bridge import BridgeClient
            if not self.bridge:self.bridge=BridgeClient(self,self.store.path.parent/'editor')
            snapshot=self.bridge.call('read',b['name'])
            rows=snapshot['rows'];records.index(rows,b)
            return rows,snapshot,None
        p=path_in(self.root,b['path']);raw=read_bytes(p)
        return records.load(raw,b.get('format','json'),b),raw,p

    def _data_read(self,b,view,where,fields,limit,offset):
        rows,_,_=self._snapshot(b)
        if view=='brief':return {'brief':b.get('brief',''),'count':len(rows)}
        if view in {'auto','overview','details','documentation'}:
            evidence=[]
            for term in b.get('consumers',[]):
                evidence.extend(project.usage(self.root,term,2))
            return {'brief':b.get('brief',''),'key':b['key'],'fields':b['fields'],
                    'count':len(rows),'existing_use':evidence[:5],
                    'sample':rows[:min(2,limit)],'data_format':b.get('format','json')}
        if view!='rows':raise SafeError('数据视图为 brief/overview/rows；不把二进制资产读成代码。')
        if set(where)-b['fields'].keys() or set(fields)-b['fields'].keys():raise SafeError('查询字段不存在。')
        selected=[r for r in rows if all(r.get(k)==v for k,v in where.items())]
        shown=selected[offset:offset+limit]
        if fields:shown=[{k:r[k] for k in fields if k in r} for r in shown]
        return {'rows':shown,'total':len(selected),**({'next_offset':offset+limit} if offset+limit<len(selected) else {})}

    def read(self,query='',name='',path='',kind='',view='auto',limit=1,offset=0,fields=None,where=None,select=None,part='body',base='HEAD',target='WORKTREE',detail=False):
        fields=fields or [];where=where or {}
        if query and (name or path):raise SafeError('搜索 query 与精确 name/path 分开使用。')
        if view=='project':return project.inventory(self.root,self.profile.bindings,limit=max(limit,20),offset=offset)
        if view=='plan':
            if not self.pending: return {'status':'no_plan'}
            return self.plan_summary
        if view=='uses':
            term=query or name or (self.target or {}).get('name','')
            return {'evidence_kind':'textual_locations_not_semantic_calls','uses':project.usage(self.root,term.rsplit('::',1)[-1],limit)}
        if view in ('changes','history','inventory'):
            if target=='PLAN' and self.pending and self.pending.kind in ('data','asset'):return self.plan_summary
            with self.code.catalog.request():return self.code.read(view=view,name=name,path=path,base=base,target=target,detail=detail,limit=limit,offset=offset)
        if query:
            hits=[];words=tokens(query);aliases=self.profile.data.get('aliases',{})
            expanded=list(words)
            for word in words:
                for k,v in aliases.items():
                    if k in word:expanded+=tokens(' '.join(v) if isinstance(v,list) else str(v))
            for b in self.profile.bindings.values():
                text=' '.join([b['name'],b.get('brief',''),b['path'],*b['fields']]).casefold()
                matched=sum(1 for w in expanded if w in text)
                if matched: hits.append((100 if query.casefold()==b['name'].casefold() else 35+30*matched/max(1,len(expanded)),'data',b))
            source_error=''
            if kind not in {'data','asset'} and not (self.profile.mode=='content' and hits and kind!='code'):
                try:
                    from doxygenue.search import rank
                    with self.code.catalog.request():
                        self.code.catalog.ensure()
                        for s,score,reason,exact in rank(self.code.catalog.symbols,query,self.code.catalog.settings['aliases'],self.code.scope,''):
                            # Repository descriptions and identifier tokens participate in the same retrieval.
                            hits.append((score/10,'code',s))
                except SafeError as e:source_error=str(e)
            if kind=='code':hits=[h for h in hits if h[1]=='code']
            hits.sort(key=lambda h:(-h[0],h[1],h[2]['name'] if h[1]=='data' else h[2].name))
            selected=hits[offset:offset+limit]
            if limit!=1 or not selected:
                result={'results':[{'name':s['name'] if d=='data' else s.name,'kind':d,'brief':s.get('brief','') if d=='data' else s.brief} for _,d,s in selected],'total':len(hits)}
                if source_error:result['code_index_error']=source_error
                return result
            _,domain,obj=selected[0];actual=obj['name'] if domain=='data' else obj.name
            if select is not False:self._set_target(actual,obj['path'] if domain=='data' else str(Path(obj.file).relative_to(self.root)),domain)
            requested='brief' if view=='auto' else view
            if domain=='data':out=self._data_read(obj,requested,where,fields,limit,offset)
            else:out=self._read_code(actual,str(Path(obj.file).relative_to(self.root)),requested,part,select=False)
            result={'name':actual,'kind':domain,**out}
            if source_error:result['code_index_error']=source_error
            if query.casefold()!=actual.casefold():result['match']='ranked_candidate'
            return result
        domain=self._domain(name,path,kind)
        if domain=='data':return self._data_read(self._binding(name,path),view,where,fields,limit,offset)
        if not name and not path and self.target and self.target['kind']=='code':name=self.target['name'];path=self.target.get('path','')
        return self._read_code(name,path,'overview' if view=='auto' else view,part,select)

    def _read_code(self,name,path,view,part,select):
        with self.code.catalog.request():
            # Resolve an exact compound before function leaf-name fallback (e.g. its constructor).
            if name and view in ('brief','overview','details','documentation'):
                from doxygenue.source_docs import inventory
                matches=[e for e in inventory(self.code.catalog)
                    if e.kind in ('class','struct','union','namespace') and e.name==name
                    and inside(e.file,self.code.scope)
                    and (not path or canonical(Path(self.root)/path)==e.file)]
                if len(matches)>1:raise SafeError('类或命名空间不唯一；请补充 path。')
                if matches:
                    e=matches[0]
                    return {'name':e.name,'kind':e.kind,'signature':e.signature,
                        'documentation':e.documentation if view!='brief' else
                            {'brief':e.documentation.get('brief','')}}
            out=self.code.read(name=name,path=path,view=view,part=part,select=False)
            result=compact_result('Read',out,{'view':view})
            # Reflection specifiers are behavior, not comment decoration.
            if view in ('overview','details','documentation'):
                s=self.code._resolve_symbol(name,path);p=Path(s.file)
                from .project import ue_specifiers
                marker=ue_specifiers(read_bytes(p).decode('utf-8-sig'),s.line,s.name.rsplit('::',1)[-1])
                if marker:result['ue_specifiers']=marker
            if select:self._set_target(out['name'],out['target']['path'],'code')
            return result

    def _set_target(self,name,path,kind):
        self.abort()
        if kind=='data':
            b=self.profile.find_binding(name,path);self.target={'name':b['name'],'path':b['path'],'kind':'data'}
        else:
            self.code.configure(action='target',name=name,path=path)
            self.target={'kind':'code',**self.code.default_locator}
        self.parent=self.target['name'].rpartition('::')[0]
        self.remembered[self.parent]=copy.deepcopy(self.target)
        return {'target':self.target}

    def _reference_guards(self,b,newrows,deleted=False):
        guards={}
        for field,other in b.get('references',{}).items():
            ref=self.profile.bindings[other];rows,raw,p=self._snapshot(ref)
            keys={records.identity(r[ref['key']],ref) for r in rows}
            for row in newrows:
                if field in row and row[field] not in (None,'') and records.identity(row[field],ref) not in keys:
                    raise SafeError(f'引用不存在：{field}={row[field]} → {other}')
            if p:guards[canonical(p)]=raw
        # Refuse deleting rows still referenced by registered tables.
        if deleted:
            keys={records.identity(r[b['key']],b) for r in newrows}
            for other in self.profile.bindings.values():
                for field,ref in other.get('references',{}).items():
                    if ref!=b['name']:continue
                    rows,raw,p=self._snapshot(other)
                    for row in rows:
                        if row.get(field) not in ('',None) and records.identity(row[field],b) not in keys:raise SafeError('记录仍被 '+other['name']+'.'+field+' 引用，先维护引用。')
                    if p:guards[canonical(p)]=raw
        return guards

    def _data_plan(self,action,name,path,rows,keys,import_file,mapping,reason):
        self.profile.authorize('data');b=self._binding(name,path)
        old,snapshot,p=self._snapshot(b);source_guard={}
        if import_file:
            if rows:raise SafeError('rows 与 import_file 不能同时给出。')
            rows,sp,sraw=records.import_rows(self.root,import_file,mapping,b);source_guard[canonical(sp)]=sraw
        if action=='Write':new,delta=records.merge(old,rows or [],b)
        else:new,delta=records.remove(old,keys,b)
        guards={**source_guard,**self._reference_guards(b,new,action=='Delete')}
        if not delta:self.abort();return {'status':'unchanged','changed_rows':0}
        if b.get('format')=='ue_datatable':
            from .bridge import AssetPlan
            plan=AssetPlan(self,action,b,old,new,snapshot,guards,reason)
        else:
            raw=records.render(snapshot,new,b)
            plan=Plan(action,'data',self.code.target,self.store.epoch(),[(canonical(p),snapshot,raw)],guards,
                      [('data:'+b['name'],canonical(p),True)],reason,{'name':b['name'],'path':b['path']})
        self.code.plan=plan;self.pending=plan;self.plan_profile=self.profile.fingerprint
        shown,clipped=records.compact_changes(delta)
        self.plan_summary={'status':'preview','plan':plan.id,'name':b['name'],'changed_rows':len(delta),
                           'rows':shown,'unchanged_rows':len(old)-sum(d['change']!='add' for d in delta),
                           'runtime_code_changed':False,'full_changes_local':clipped}
        # Complete details remain local for GUI and destructive approval, not every model response.
        from doxygenue.doxygen import dump_atomic
        dump_atomic(self.store.path.parent/'plans'/(plan.id+'.json'),{**self.plan_summary,'rows':delta})
        if action=='Delete':
            if b.get('format')=='ue_datatable':plan.register_approval(self)
            else:
                from doxygenue.approvals import register
                register(self.code)
            self.plan_summary['approval']='local_user_required'
        return self.plan_summary

    def _analyze_code_plan(self,plan):
        added=collections.Counter();signals=[]
        for path,old,new in plan.changes:
            before=collections.Counter(t.value for t in lex((old or b'').decode('utf-8-sig'))[0])
            after=collections.Counter(t.value for t in lex((new or b'').decode('utf-8-sig'))[0])
            added+=after-before
        for symbol in ('new','delete','Tick','SetTimer','GetAllActorsOfClass','TActorIterator','static'):
            if added[symbol]:signals.append({'introduced':symbol,'count':added[symbol]})
        blocked=[s for s in self.profile.data.get('forbid_added_tokens',[]) if added[s]]
        if blocked:raise SafeError('违反用户维护约定，新增了：'+', '.join(blocked)+'。复用已有数据/接口；这不是可由MCP忽略的警告。')
        return signals

    def write(self,action='preview',kind='',name='',path='',old_code='',new_code='',operation='modify',part='declaration',fields=None,rows=None,import_file='',mapping=None,plan='',includes=None,placement='after',comment_id='',members=None):
        if action=='apply':
            if any((name,path,old_code,new_code,fields,rows,import_file,mapping,includes,comment_id,members)):raise SafeError('apply 仅使用已有 plan，不接受新载荷。')
            return self._apply('Write',plan)
        if action!='preview':raise SafeError('Write 为 preview/apply，不需要强制 Prepare。')
        self.abort()
        if operation=='replace_tank_asset_paths':
            if kind!='data' or not path or any((name,old_code,new_code,fields,rows,import_file,mapping,includes,comment_id)):
                raise SafeError('JSON 坦克路径替换仅接受明确文件及 old_code/new_code 清单。')
            return self._json_tank_path_plan(path,members or [])
        if operation=='replace_focus_tank_paths':
            if kind!='data' or not path or any((name,old_code,new_code,fields,rows,import_file,mapping,includes,comment_id)):
                raise SafeError('科技坦克路径替换仅接受明确文件及 old_code/new_code 清单。')
            return self._json_focus_tank_plan(path,members or [])
        if operation=='replace_focus_tank_description':
            if kind!='data' or not path or any((name,fields,rows,import_file,mapping,includes,comment_id,members)):
                raise SafeError('科技描述替换仅接受明确文件和旧/新描述。')
            return self._json_focus_description_plan(path,old_code,new_code)
        domain='data' if rows is not None or import_file else self._domain(name,path,kind)
        if domain=='data':
            if fields or old_code or new_code or includes or members:raise SafeError('数据增改使用 rows/import_file，不接受代码载荷。')
            return self._data_plan('Write',name,path,rows,[],import_file,mapping,'')
        self.profile.authorize('code')
        if operation!='function' and kind!='function' and not name and not path and self.target and self.target['kind']=='code':name=self.target['name'];path=self.target.get('path','')
        k=kind or 'code'
        if k=='function':operation='function';k='code'
        if k=='include':operation='include';k='code'
        with self.code.catalog.request():
            out=self.code.write(action='preview',kind=k,name=name,path=path,old_code=old_code,new_code=new_code,
                                operation=operation,part=part,fields=fields,members=members,includes=includes,placement=placement,comment_id=comment_id)
        p=self.code.plan
        if not p:
            if out.get('status')=='unchanged':return compact_result('Write',out,{'action':'preview'})
            raise SafeError('没有生成可提交计划。')
        try:
            self.profile.authorize(k,[x[0] for x in p.changes]);signals=self._analyze_code_plan(p)
            if self.profile.data.get('require_validation') and not self.code.validator:raise SafeError('本维护配置要求真实验证，但尚未配置。')
        except Exception:self.abort();raise
        self.pending=p;self.plan_profile=self.profile.fingerprint
        result=compact_result('Write',out,{'action':'preview'})
        result['plan']=result.pop('preview_id');result.pop('reuse_candidates',None)
        if signals:result['review_signals']=signals
        if k=='code':
            from tools.check_localization import unlocalized_literals_added
            literals=unlocalized_literals_added(old_code,new_code)
            if literals:result['localization_warnings']={'ungatherable_literals':literals,'remedy':'Use existing localized FText or LOCTEXT/NSLOCTEXT/string-table identity.'}
        self.plan_summary=result
        return result

    def _json_tank_path_plan(self,path,members):
        target=self.profile.authorize_json_path_patch(path)
        if not members or len(members)>16 or Path(target).is_symlink():
            raise SafeError('JSON 坦克路径替换需要有界清单和普通文件。')
        raw=read_bytes(target)
        document=json_load(raw.decode('utf-8-sig'))
        if not isinstance(document,dict) or not isinstance(document.get('scenarios'),list):
            raise SafeError('战略配置 JSON 缺少 scenarios 数组。')
        changed=copy.deepcopy(document)
        text=raw.decode('utf-8-sig')
        counts={}
        for item in members:
            old=item.get('old_code','')
            new=item.get('new_code','')
            if (not old.startswith('/Game/Unit/Actor/Army/Tank/')
                    or not new.startswith('/Game/Unit/Actor/Army/Tank/Common/Gen_Common_')
                    or old==new or old in counts):
                raise SafeError('只能把明确的旧坦克路径改为通用坦克路径。')
            count=0
            for scenario in changed['scenarios']:
                for force in scenario.get('initialForces',[]):
                    if force.get('unitConfig')==old:
                        force['unitConfig']=new
                        count+=1
            if count==0 or text.count(json.dumps(old,ensure_ascii=False))!=count:
                raise SafeError('旧坦克路径在 initialForces 中未唯一对应 JSON 字符串值。')
            text=text.replace(json.dumps(old,ensure_ascii=False),json.dumps(new,ensure_ascii=False))
            counts[old]=count
        if json_load(text)!=changed:
            raise SafeError('JSON 替换影响了非目标数据。')
        bom=b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
        updated=bom+text.encode('utf-8')
        p=Plan('Write','json_path_patch',self.code.target,self.store.epoch(),
               [(target,raw,updated)],{},[('data:StrategicProfiles',target,True)],'',
               {'name':'StrategicProfiles','path':path})
        self.code.plan=p;self.pending=p;self.plan_profile=self.profile.fingerprint
        result=p.preview(self.root)
        result['plan']=result.pop('preview_id')
        result['changed_paths']=counts
        self.plan_summary=result
        return result

    def _json_focus_tank_plan(self,path,members):
        target=self.profile.authorize_json_path_patch(path)
        if not path.endswith('Germany1939NationalFocuses.json') or not members or len(members)>16 or Path(target).is_symlink():
            raise SafeError('科技坦克路径替换需要批准的现有科技配置和有界清单。')
        raw=read_bytes(target)
        document=json_load(raw.decode('utf-8-sig'))
        if not isinstance(document,dict) or not isinstance(document.get('technologies'),list):
            raise SafeError('科技配置 JSON 缺少 technologies 数组。')
        text=raw.decode('utf-8-sig')
        counts={}
        replacements={}
        for item in members:
            old=item.get('old_code','')
            new=item.get('new_code','')
            if (not old.startswith('/Game/Unit/Actor/Army/Tank/')
                    or '/Common/' in old
                    or not new.startswith('/Game/Unit/Actor/Army/Tank/Common/Gen_Common_')
                    or old==new or old in counts):
                raise SafeError('只能把明确的旧坦克路径改为通用坦克路径。')
            old_id=old.rsplit('/',1)[-1].split('.',1)[0]
            new_id=new.rsplit('/',1)[-1].split('.',1)[0]
            if (not old.endswith('/'+old_id+'.'+old_id)
                    or not new.endswith('/'+new_id+'.'+new_id)
                    or old_id in replacements):
                raise SafeError('坦克路径和资产名称必须一致且唯一。')
            replacements[old_id]=(old,new,new_id)
            counts[old]=0
        expected=copy.deepcopy(document)
        for tech in expected['technologies']:
            for grant in tech.get('forceGrants',[]):
                for entry in [grant,*grant.get('onArrivalGrants',[])]:
                    value=entry.get('configAssetPath')
                    for old,new,_ in replacements.values():
                        if value==old:entry['configAssetPath']=new;counts[old]+=1
            mapping=tech.get('historicalMapping',{})
            for formation in mapping.get('historical_formations',[]):
                value=formation.get('config_asset_path')
                for old_id,(old,new,new_id) in replacements.items():
                    if value==old:
                        if formation.get('game_unit_id')!=old_id:raise SafeError('史实编队单位 ID 与资产路径不一致。')
                        formation['config_asset_path']=new
                        formation['game_unit_id']=new_id
                        counts[old]+=1
            for total in mapping.get('totals',{}).values():
                if not isinstance(total,dict) or not isinstance(total.get('unit_counts'),dict):continue
                unit_counts=total['unit_counts']
                renamed={replacements.get(key,(None,None,key))[2]:value for key,value in unit_counts.items()}
                if len(renamed)!=len(unit_counts):raise SafeError('通用单位 ID 在同一统计中冲突。')
                total['unit_counts']=renamed
        for old_id,(old,new,new_id) in replacements.items():
            if not counts[old]:raise SafeError('科技配置中未找到旧坦克路径：'+old_id)
            old_literal=json.dumps(old,ensure_ascii=False)
            old_id_literal=json.dumps(old_id,ensure_ascii=False)
            if text.count(old_literal)!=counts[old]:raise SafeError('旧资产路径出现在非目标字段。')
            text=text.replace(old_literal,json.dumps(new,ensure_ascii=False))
            text=text.replace(old_id_literal,json.dumps(new_id,ensure_ascii=False))
        if json_load(text)!=expected:raise SafeError('科技配置替换影响了非目标数据。')
        bom=b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
        p=Plan('Write','json_path_patch',self.code.target,self.store.epoch(),
               [(target,raw,bom+text.encode('utf-8'))],{},[('data:NationalFocuses',target,True)],'',
               {'name':'NationalFocuses','path':path})
        self.code.plan=p;self.pending=p;self.plan_profile=self.profile.fingerprint
        result=p.preview(self.root)
        result['plan']=result.pop('preview_id')
        result['changed_paths']=counts
        self.plan_summary=result
        return result

    def _json_focus_description_plan(self,path,old_code,new_code):
        target=self.profile.authorize_json_path_patch(path)
        if (Path(target).is_symlink() or not path.endswith('NationalFocuses.json')
                or old_code!='完成后部署745个步兵团（改进步枪）、14个Germany_Panzer_IV_Ausf_D单位，按各方向预设路线行动。部队完成各自整条路线后才交由玩家控制。'
                or new_code!='完成后部署745个步兵团（改进步枪）、14个通用改进型中型坦克单位，按各方向预设路线行动。部队完成各自整条路线后才交由玩家控制。'):
            raise SafeError('只能更新巴巴罗萨国策中的旧坦克名称。')
        raw=read_bytes(target)
        text=raw.decode('utf-8-sig')
        document=json_load(text)
        expected=copy.deepcopy(document)
        if 'technologies' in expected:
            rows=[tech for tech in expected['technologies'] if tech.get('id')=='Barbarossa']
            if len(rows)!=1 or rows[0].get('description')!=old_code:
                raise SafeError('巴巴罗萨国策描述不存在或不唯一。')
            rows[0]['description']=new_code
        else:
            strings=expected.get('text') if isinstance(expected,dict) else None
            if not isinstance(strings,dict) or strings.get('focus.germany1939.Barbarossa.description')!=old_code:
                raise SafeError('本地化巴巴罗萨描述不存在。')
            strings['focus.germany1939.Barbarossa.description']=new_code
        literal=json.dumps(old_code,ensure_ascii=False)
        if text.count(literal)!=1:raise SafeError('旧描述在 JSON 中未唯一出现。')
        text=text.replace(literal,json.dumps(new_code,ensure_ascii=False))
        if json_load(text)!=expected:raise SafeError('描述替换影响了其他数据。')
        bom=b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
        p=Plan('Write','json_path_patch',self.code.target,self.store.epoch(),
               [(target,raw,bom+text.encode('utf-8'))],{},[('data:NationalFocuses',target,True)],'',
               {'name':'NationalFocuses','path':path})
        self.code.plan=p;self.pending=p;self.plan_profile=self.profile.fingerprint
        result=p.preview(self.root)
        result['plan']=result.pop('preview_id')
        self.plan_summary=result
        return result

    def delete(self,action='preview',kind='',name='',path='',keys=None,old_code='',part='body',comment_id='',reason='',plan=''):
        if action=='apply':
            if any((name,path,keys,old_code,comment_id,reason)):raise SafeError('apply 不接受新载荷。')
            return self._apply('Delete',plan)
        if action!='preview' or not reason.strip():raise SafeError('删除需要明确 reason；它不是用户身份认证。')
        self.abort()
        if kind=='data' and path.endswith('DefaultRTSInputSystem.ini'):
            if any((name,keys,old_code,comment_id)):
                raise SafeError('旧坦克协议清理只接受明确 INI 路径和删除理由。')
            return self._prune_legacy_tank_protocols(path,reason)
        if keys is not None or self._domain(name,path,kind)=='data':return self._data_plan('Delete',name,path,[],keys,'',{},reason)
        self.profile.authorize('code')
        if not name and not path and self.target and self.target['kind']=='code':name=self.target['name'];path=self.target.get('path','')
        with self.code.catalog.request():
            out=self.code.delete(kind=kind or 'code',name=name,path=path,old_code=old_code,part=part,comment_id=comment_id,reason=reason)
        p=self.code.plan
        try:self.profile.authorize('code',[x[0] for x in p.changes])
        except Exception:self.abort();raise
        self.pending=p;self.plan_profile=self.profile.fingerprint
        result=compact_result('Delete',out,{});result['plan']=result.pop('preview_id');self.plan_summary=result
        return result

    def _prune_legacy_tank_protocols(self,path,reason):
        expected='Plugins/RTSInputSystem/Config/DefaultRTSInputSystem.ini'
        if path.replace('\\','/')!=expected:
            raise SafeError('只能清理 RTSInputSystem 插件默认协议中的旧坦克。')
        target=self.profile.authorize_ini_tank_protocol_prune(path)
        if Path(target).is_symlink():raise SafeError('不能修改链接文件。')
        raw=read_bytes(target)
        text=raw.decode('utf-8-sig')
        lines=text.splitlines(keepends=True)
        prefix='+massUnitTypeProtocols='
        tank='UnitAssetPath="/Game/Unit/Actor/Army/Tank/'
        removed=[line for line in lines if line.startswith(prefix) and tank in line]
        if len(removed)!=45 or any('/Common/' in line or '/Skins/' in line for line in removed):
            raise SafeError('插件默认协议不是预期的 45 条旧坦克记录。')
        updated=''.join(line for line in lines if line not in removed)
        if updated.count(prefix)!=text.count(prefix)-45:
            raise SafeError('坦克协议删除范围不正确。')
        bom=b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
        p=Plan('Delete','ini_tank_protocol_prune',self.code.target,self.store.epoch(),
               [(target,raw,bom+updated.encode('utf-8'))],{},[('data:DefaultRTSInputSystem',target,True)],reason,
               {'name':'DefaultRTSInputSystem','path':path})
        self.code.plan=p;self.pending=p;self.plan_profile=self.profile.fingerprint
        result=p.preview(self.root)
        result['plan']=result.pop('preview_id')
        result['removed_tank_protocols']=45
        self.plan_summary=result
        return result

    def _apply(self,action,id):
        self.profile.assert_current()
        p=self.pending
        if not p or p.id!=id or p.action!=action or self.plan_profile!=self.profile.fingerprint:raise SafeError('无当前会话的对应计划；Write不能提交Delete。')
        if p.kind=='json_path_patch':self.profile.authorize_json_path_patch(p.locator['path'])
        elif p.kind=='ini_tank_protocol_prune':self.profile.authorize_ini_tank_protocol_prune(p.locator['path'])
        else:self.profile.authorize('data' if p.kind in ('data','asset') else 'code',[] if p.kind in ('data','asset') else [x[0] for x in p.changes])
        if p.kind=='data':
            b=self.profile.find_binding(p.locator['name'],p.locator['path'])
            new=records.load(p.changes[0][2],b.get('format','json'),b)
            self._reference_guards(b,new,p.action=='Delete')
        if p.kind=='asset':out=p.apply(self)
        else:out=p.apply(self.code)
        self.pending=None;self.plan_summary=None;self.code.plan=None
        validation=out.get('validation',{})
        result={'status':out['status'],'files':out.get('files',[]),'validation':validation.get('status','not_configured')}
        if 'receipt' in out:result['receipt']=out['receipt']
        return result

    def configure(self,action='status',name='',path='',kind='',reason='',output_format='html',limit=20):
        if action=='check_localization':
            from tools.check_localization import gather_entries,read_archives,find_gaps
            target=name or 'Game'
            manifest=path_in(self.root,path or f'Content/Localization/{target}/{target}.manifest')
            entries=gather_entries(manifest)
            rows=read_archives([f'{language}={manifest.parent/culture/(manifest.stem+".archive")}'
                                for language,culture in [('zh','zh-Hans-CN'),('en','en')]])
            gaps=find_gaps(entries,rows)
            return {'manifest':str(manifest),'gathered':len(entries),'missing':len(gaps),
                    'gaps':gaps[:limit],'has_more':len(gaps)>limit,
                    'coverage':'Native gathered FText only; FString/invariant text requires inspection'}
        if action=='status':return {'mode':self.profile.mode,'profile':self.profile.data.get('label','未授权，只读'),'target':self.target,'data':[b['name'] for b in self.profile.bindings.values()],'validator':bool(self.code.validator),'plan':self.pending.id if self.pending else None}
        if action=='target':return self._set_target(name,path,self._domain(name,path,kind))
        if action=='parent':
            self.abort();self.target=None
            if self.code.target:self.code.configure(action='parent')
            else:self.parent=self.parent.rpartition('::')[0]
            return {'parent':self.parent}
        if action=='child':
            t=self.remembered.get(self.parent)
            if t and not name:return self._set_target(t['name'],t.get('path',''),t['kind'])
            with self.code.catalog.request():self.code.configure(action='child',name=name)
            self.target={'kind':'code',**self.code.default_locator} if self.code.default_locator else None
            return {'target':self.target,'parent':self.code.container}
        if action=='scope':self.abort();self.target=None;return self.code.configure(action='scope',path=path)
        if action=='abort':return self.abort()
        if action in ('lock','lock_status') and self._domain(name,path,kind)=='data':
            b=self._binding(name,path)
            if b.get('format')=='ue_datatable':
                from .bridge import asset_lock_path
                p=asset_lock_path(self.root,b['path'])
            else:p=canonical(path_in(self.root,b['path']))
            if action=='lock':self.store.lock(self.root,'data:'+b['name'],[{'name':'data:'+b['name'],'path':p}],reason);self.abort()
            return {'locked':bool(self.store.blocked('data:'+b['name'],p,all_file=True))}
        allowed={'validate','check_comments','export_docs','lock','lock_status','reindex','approvals','policy'}
        if action not in allowed:raise SafeError('未知动作；无MCP批准/解锁/改规则/任意执行入口。')
        with self.code.catalog.request():return self.code.configure(action=action,name=name,path=path,reason=reason,output_format=output_format,limit=limit)
