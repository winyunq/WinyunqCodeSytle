"""Small, explicit observability views. No whole-source fallback."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from .cpp import SafeError,Source,EXTENSIONS,EXCLUDED,sha,inside

CAPABILITIES={
 'version':'0.3.0','fully_controllable':False,
 'tools':['Read','Write','Delete','Configure'],
 'cost_order':['Read','Write.preview→Write.apply','Delete.preview→local_user_approval→Delete.apply'],
 'supported':['symbol_search','brief_overview_full_docs','local_code_edit','cpp_header_pair',
              'include_edit','source_comment_fields','independent_delete','function_diff',
              'policy_check','accepted_issue_baseline','release_gate','local_rollback'],
 'conditional':['function_templates','conditional_branch_edits','unique_member_signature_sync','native_pdf_with_xelatex','project_build_with_profile'],
 'not_supported':['arbitrary_language_edit','automatic_Blueprint_or_UHT_refactor','arbitrary_cpp_class_template_signature',
                  'automatic_all_callers_rewrite','automatic_Build_cs_or_project_config_edit','prove_doc_semantic_truth','OS_sandbox_against_same_user'],
 'user_only':['approve_delete','unlock','import_quality_rules','accept_issue_baseline','restore_transaction']}


def inventory(engine,limit=50,offset=0):
    engine.catalog.ensure()
    sources=[p for p in engine.catalog.scan() if p.suffix.lower() in EXTENSIONS]
    rows=[]
    for p in sources:
        try:
            source=Source.load(p);count=len(source.occurrences);unsafe=sum(o.unsafe for o in source.occurrences)
            editability='partial' if unsafe else 'range_verified'
            reason='个别宏/条件编译范围只读' if unsafe else ''
        except (SafeError,UnicodeError,OSError) as exc:editability='doxygen_read_only';reason=str(exc);count=0;unsafe=0
        rows.append({'path':p.relative_to(engine.root).as_posix(),'editability':editability,'occurrences':count,
                     **({'reason':reason} if reason else {})})
    return {'files':rows[offset:offset+limit],'total_files':len(rows),'symbols':len(engine.catalog.symbols),
            'next_offset':offset+limit if offset+limit<len(rows) else None,
            'excluded_directories':sorted(EXCLUDED|set(engine.catalog.settings['exclude'])),
            'meaning':'range_verified表示词法范围可复核，不表示任意C++变换正确；生成/排除/预处理不可见代码不算全量验证。'}


def impact(engine,name='',path='',limit=30,offset=0):
    s=engine._resolve_symbol(name,path);leaf=s.name.rsplit('::',1)[-1]
    result=[];unresolved=[]
    for p in engine.catalog.scan():
        if p.suffix.lower() not in EXTENSIONS:continue
        try:src=Source.load(p)
        except (SafeError,UnicodeError,OSError) as exc:unresolved.append({'path':p.relative_to(engine.root).as_posix(),'reason':str(exc)});continue
        for t in src.tokens:
            if t.value!=leaf:continue
            owners=[o.name for o in src.occurrences if o.start<=t.start<o.end]
            result.append({'path':p.relative_to(engine.root).as_posix(),'line':src.text.count('\n',0,t.start)+1,
                           'owner':owners[0] if len(owners)==1 else None})
    return {'name':s.name,'basis':'lexical_mentions_not_proven_call_graph','results':result[offset:offset+limit],
            'total':len(result),'next_offset':offset+limit if offset+limit<len(result) else None,'unresolved':unresolved[:limit]}


def history(engine,limit=20):
    folder=engine.store.path.parent/'doxygenue-transactions';records=[]
    for p in sorted(folder.glob('*/journal.json'),reverse=True):
        try:r=json.loads(p.read_text(encoding='utf-8'))
        except (ValueError,OSError):continue
        if r.get('root')!=engine.root:continue
        records.append({'id':p.parent.name,'status':r['status'],'action':r.get('action'),'kind':r.get('kind'),
                        'files':[os.path.relpath(f['path'],engine.root) for f in r.get('files',[])],
                        'restorable':r['status']=='applied' and all('after_hash' in f for f in r.get('files',[]))})
    return {'transactions':records[:limit],'total':len(records),'restore':'本机用户审阅后可恢复；MCP无整文件回滚旁路。'}


def user_restore(store,root,transaction_id):
    """Explicit local restore to recorded before bytes, only from exact after state."""
    from .cpp import canonical
    from .transactions import atomic_replace
    from .doxygen import dump_atomic
    if not re.fullmatch(r'[0-9]+-[0-9a-f]{20}',transaction_id):raise SafeError('事务ID无效。')
    folder=store.path.parent/'doxygenue-transactions'/transaction_id;file=folder/'journal.json'
    r=json.loads(file.read_text(encoding='utf-8'))
    if r.get('root')!=canonical(root) or r.get('status')!='applied':raise SafeError('只能恢复本项目已完成事务。')
    changes=[]
    with store.transaction():
        for f in r['files']:
            path=Path(f['path']);current=path.read_bytes() if path.exists() else None
            if not inside(path,root) or path.is_symlink() or canonical(path)!=f['path']:raise SafeError('恢复路径不安全。')
            if 'after_hash' not in f or (None if current is None else sha(current))!=f['after_hash']:raise SafeError('事务后源码又有变化，拒绝覆盖。')
            if store.blocked('',str(path),all_file=True):raise SafeError('恢复文件包含锁；用户需先复核并解锁。')
            backup=Path(f['backup']) if f.get('backup') else None
            if backup and (not inside(backup,folder) or backup.is_symlink()):raise SafeError('备份路径不安全。')
            old=backup.read_bytes() if backup else None
            if (None if old is None else sha(old))!=f.get('before_hash'):raise SafeError('备份哈希不匹配。')
            changes.append((path,current,old))
        r['status']='restoring';dump_atomic(file,r);applied=[]
        try:
            for path,current,old in changes:
                applied.append((path,current,old));atomic_replace(path,old,current)
        except BaseException:
            okay=True
            for path,current,old in reversed(applied):
                try:
                    actual=path.read_bytes() if path.exists() else None
                    if actual==current:continue
                    if actual!=old:raise SafeError('恢复期间外部变化。')
                    atomic_replace(path,current,old)
                except BaseException:okay=False
            r['status']='applied' if okay else 'needs_recovery';dump_atomic(file,r);raise
        r['status']='rolled_back';r['local_user_restore']=True;dump_atomic(file,r);store._bump()
    return {'status':'restored','transaction':transaction_id}
