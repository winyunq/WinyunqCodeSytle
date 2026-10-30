"""Doxygen-semantic rules, accepted-issue baseline and explicit release gate."""
from __future__ import annotations
from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid
from .cpp import SafeError, canonical, clean_comment, sha, EXTENSIONS
from .doxygen import dump_atomic
from .source_docs import inventory, anchor
from . import policy


def _text(value):
    if isinstance(value,dict): return _text(value.get('description',value.get('content','')))
    if isinstance(value,list): return ' '.join(_text(v) for v in value)
    return str(value or '').strip()


def semantic_issues(engine,e,p):
    """Meaning comes from Doxygen XML, never a second @param regex parser."""
    d=e.documentation; full=d.get('full',{}); issues=[]; local=None; raw=''
    try:
        src,at,comments=anchor(engine.catalog,e)
        recognized=[c for c in comments if c.value.startswith(('/**','/*!','///','//!'))]
        raw='\n'.join(clean_comment(c.value) for c in recognized)
        local=bool(raw.strip())
    except (SafeError,OSError,UnicodeError):
        recognized=[]
    documented=bool(d.get('brief') or full)
    if not documented: issues.append(('brief','missing_doxygen_comment'))
    elif not _text(d.get('brief')): issues.append(('brief','missing_brief'))
    if not _text(full.get('details')): issues.append(('details','missing_details'))
    if not p['allow_shared_documentation'] and local is not True:
        issues.append(('local_comment','shared_or_unresolved_documentation'))
    elif local is False: issues.append(('local_comment','missing_local_comment'))
    elif local is None and not p['allow_shared_documentation']: issues.append(('resolution','unresolved_source_comment'))
    for key,expected,tag in [('params',e.params,'param'),('tparams',e.tparams,'tparam')]:
        found=d.get(key,{})
        for i,name in enumerate(expected):
            # Doxygen permits ordinal/dash documentation of unnamed parameters.
            candidates=[name] if name else [str(i+1),'-']
            located=next((n for n in candidates if n in found),None)
            if located is None: issues.append((key,'missing_'+tag+':'+(name or str(i+1))))
            elif not _text(found[located]): issues.append((key,'empty_'+tag+':'+(name or str(i+1))))
        for name in found:
            valid=name in expected or (not all(expected) and (name=='-' or name.isdigit() and 1<=int(name)<=len(expected)))
            if not valid: issues.append(('parameter_names','unknown_'+tag+':'+name))
        for c,n in e.documentation_counts.items():
            prefix='templateparam:' if tag=='tparam' else 'param:'
            if c.startswith(prefix) and n>1 and not (c==prefix+'-' and expected.count('')>=n):
                issues.append(('duplicates','duplicate_'+tag+':'+c[len(prefix):]))
    leaf=e.name.rsplit('::',1)[-1];parent=e.name.rpartition('::')[0].rsplit('::',1)[-1]
    typ=re.sub(r'\b(?:virtual|static|inline|constexpr|consteval|explicit|friend)\b','',e.return_type).strip()
    if e.kind=='function' and leaf not in {parent,'~'+parent} and typ not in {'','void'} and not _text(d.get('returns')) and not d.get('return_values'):
        issues.append(('returns','missing_return'))
    if re.search(r'\b(TODO|TBD|FIXME)\b|待补充|待完善',json.dumps(d,ensure_ascii=False),re.I):
        issues.append(('placeholder','placeholder_documentation'))
    for c in recognized:
        if '\n' in c.value and c.value.startswith('/*'):
            cols=[len(s.expandtabs(4))-len(s.expandtabs(4).lstrip()) for s in c.value.splitlines()[1:] if s.lstrip().startswith('*')]
            if len(set(cols))>1: issues.append(('format','misaligned_comment_stars'))
    return issues,local


def source_snapshot(engine):
    files=engine.catalog.scan()
    return {Path(f).relative_to(engine.root).as_posix():sha(f.read_bytes()) for f in files}


def audit(engine,path='',public_only=True,limit=50,full_root=False,changed_only=False,base='HEAD'):
    from .doc_pipeline import selected_files,run_doxygen
    start=time.perf_counter();p=policy.load(engine.store,engine.root)
    original_scope=engine.scope
    try:
        if full_root: engine.scope=engine.root
        files=selected_files(engine,path)
    finally: engine.scope=original_scope
    allowed={canonical(f) for f in files};engine.catalog.ensure()
    entities=[e for e in inventory(engine.catalog) if e.file in allowed and (not public_only or e.protection=='public')]
    changed_names=None;change_report=None
    if changed_only:
        from .changes import compare
        change_report=compare(engine,base=base,target='WORKTREE',limit=20000)
        changed_names={r['name'] for r in change_report['functions'] if r['change']!='removed'}
        touched={r['path'] for r in change_report['unclassified']}
        entities=[e for e in entities if e.name in changed_names or Path(e.file).relative_to(engine.root).as_posix() in touched]
    rows=[];active=[];ignored=[]
    for e in entities:
        relative=Path(e.file).relative_to(engine.root).as_posix()
        issues,local=semantic_issues(engine,e,p);findings=[];exemptions=[]
        for rule,code in issues:
            level=policy.severity(p,rule,e,relative)
            if not p['allow_shared_documentation'] and rule=='local_comment' and level=='off':level='error'
            if level=='off':continue
            reason=policy.exemption(p,rule,e,relative)
            item={'rule':rule,'code':code,'severity':level}
            fid=policy.digest([relative,e.name,e.kind,e.args,rule,code])
            item['fingerprint']=fid
            if reason:item['exemption']=reason;exemptions.append(item);ignored.append(item)
            else:findings.append(item);active.append(item)
        rows.append({'name':e.name,'kind':e.kind,'path':relative,'line':e.line,
                     'signature':e.signature,'complete':not findings,'issues':[f['code'] for f in findings],
                     'findings':findings,'exemptions':exemptions,'local_comment_verified':local,
                     'params':e.params,'tparams':e.tparams})
    folder=Path(tempfile.mkdtemp(prefix='quality-',dir=engine.catalog.cache))
    native=run_doxygen(engine,files,folder,strict=True,public_only=public_only)
    warning_text=Path(native['warnings']).read_text(encoding='utf-8',errors='replace')
    native_findings=[]
    if p['native_warnings']!='off':
        for line in warning_text.splitlines():
            if 'warning:' not in line.lower():continue
            normalized=line.replace(engine.root,'').replace('\\','/')
            normalized=re.sub(r':\d+(?::\d+)?:',':',normalized)
            native_findings.append({'rule':'native_warning','code':normalized,
                'severity':p['native_warnings'],'fingerprint':policy.digest(['native',normalized])})
    # Native warnings are whole selected-input diagnostics even in changed-only mode.
    active+=native_findings
    errors=sum(i['severity']=='error' for i in active);warnings=sum(i['severity']=='warning' for i in active)
    not_complete=[r for r in rows if not r['complete']]
    snapshot=source_snapshot(engine)
    if any(snapshot.get(Path(f).relative_to(engine.root).as_posix())!=h for f,h in native['source_hashes'].items()):
        raise SafeError('检查期间文件变化；检查结果作废。')
    counts=Counter(c.split(':',1)[0] for r in not_complete for c in r['issues'])
    fingerprints=[i['fingerprint'] for i in active if i['severity']=='error' or p['release']['block_warnings']]
    baseline=policy.metadata(engine.store,engine.root,'baseline')
    baseline_valid=bool(baseline and baseline['policy_hash']==policy.digest(p))
    existing=Counter(baseline['issues']) if baseline_valid else Counter()
    new=list((Counter(fingerprints)-existing).elements())
    report={'status':'passed' if not active else 'needs_attention','source_only':not p['allow_shared_documentation'],
        'project':engine.root,'scope':'.' if full_root else path or os.path.relpath(engine.scope,engine.root),
        'public_only':public_only,'changed_only':changed_only,'base':base if changed_only else None,
        'files':[Path(f).relative_to(engine.root).as_posix() for f in files],
        'summary':{'entities':len(rows),'complete':len(rows)-len(not_complete),'incomplete':len(not_complete),
                   'issue_count':len(active),'errors':errors,'warnings':warnings,'exempted':len(ignored),
                   'by_issue':dict(counts),'native_warning_count':native['warning_count'],'new_blocking_issues':len(new)},
        'policy_hash':policy.digest(p),'policy_name':p['name'],'baseline_valid':baseline_valid,
        'issue_fingerprints':fingerprints,'new_issue_fingerprints':new,'source_snapshot':snapshot,
        'native_doxygen':native,'entities':rows,'native_findings':native_findings,
        'coverage':{'inputs':len(files),'documentable_entities':len(rows),
                    'excluded_directory_names':sorted(set(engine.catalog.settings['exclude'])),
                    'built_in_exclusions':sorted(__import__('doxygenue.cpp',fromlist=['EXCLUDED']).EXCLUDED),
                    'limitations':['预处理非活动分支和Doxygen未识别对象不算已验证','字段完整不证明自然语言说明或运行语义正确'],
                    'changed_only_native_warnings_are_full_scope':changed_only},
        'elapsed_ms':round((time.perf_counter()-start)*1000,3)}
    dump_atomic(folder/'report.json',report)
    engine.last_quality=report
    return {k:v for k,v in report.items() if k not in {'entities','source_snapshot','issue_fingerprints','new_issue_fingerprints','native_findings'}} | {
        'report':str(folder/'report.json'),'issues':not_complete[:limit],'issues_truncated':len(not_complete)>limit}


def release(engine,output_format='html'):
    """Full trusted input scope only. No accepting check IDs from the model."""
    from .doc_pipeline import export_docs
    p=policy.load(engine.store,engine.root);policy.check_index(engine,p)
    saved_scope=engine.scope
    with engine.store.transaction():
        before=source_snapshot(engine);ph=policy.digest(p)
        engine.scope=engine.root
        try:
            report=audit(engine,public_only=p['release']['public_only'],limit=20,full_root=True)
            count=report['summary']['new_blocking_issues'] if p['release']['mode']=='no_new_errors' else report['summary']['errors']+(report['summary']['warnings'] if p['release']['block_warnings'] else 0)
            if not report['summary']['entities']:
                return {'status':'blocked','reason':'没有实际检查到的文档对象，不能发布空范围。','check':report}
            if count:
                return {'status':'blocked','reason':'文档规则门禁未通过。','blocking':count,'check':report}
            if p['release']['require_validation'] and not engine.validator:
                return {'status':'blocked','reason':'正式发布要求配置真实编译/测试；当前not_configured。','check':report}
            validation=engine.validator.run(engine.root) if engine.validator else {'status':'not_configured'}
            if source_snapshot(engine)!=before:raise SafeError('检查/验证期间源码变化；发布作废。')
            artifact=export_docs(engine,public_only=p['release']['public_only'],output_format=output_format)
            policy.check_index(engine,p)
            if source_snapshot(engine)!=before or policy.digest(policy.load(engine.store,engine.root))!=ph:
                raise SafeError('导出期间源码/规则变化；产物仅为临时文件，不是有效发布。')
            if artifact['status']!='exported':return artifact | {'publication':'not_released','check':report,'validation':validation}
            record={'status':'released','release_id':uuid.uuid4().hex[:20],'time':time.time(),
                    'policy_hash':ph,'source_snapshot':before,'validation':validation,
                    'check_report':report['report'],'artifact':artifact}
            policy.put(engine.store,engine.root,'last_release',record)
            return {k:v for k,v in record.items() if k!='source_snapshot'}
        finally:engine.scope=saved_scope
