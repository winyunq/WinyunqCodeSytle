"""Read-only function-oriented differences: Git bytes + Doxygen on BOTH sides.

No checkout, Git hooks, textconv, or external diff programs run. Every changed
file that is not safely assigned to a function remains visible as unclassified.
Overload/rename ambiguity is disclosed; this is not a compiler refactoring graph.
"""
from __future__ import annotations
from collections import defaultdict
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import shutil
from .cpp import SafeError,Source,lex,canonical,inside,sha,EXTENSIONS,EXCLUDED
from .doxygen import Catalog,dump_atomic

MAX_BYTES=128*1024*1024


def git(root,*args):
    try:
        p=subprocess.run(['git','-c','core.quotepath=false','-C',str(root),*args],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False,
                         env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0','GIT_NO_REPLACE_OBJECTS':'1'})
    except (OSError,subprocess.SubprocessError) as exc: raise SafeError('Git读取失败：'+str(exc)) from exc
    if p.returncode: raise SafeError('Git读取失败：'+p.stderr.decode('utf-8',errors='replace')[:800])
    return p.stdout


def valid_path(name):
    p=PurePosixPath(name)
    if p.is_absolute() or any(x in {'..','.'} for x in p.parts) or '\\' in name or '\x00' in name or ':' in name:
        raise SafeError('快照路径不安全：'+name)
    return p


def source_input(engine,name):
    p=valid_path(name);excluded={x.casefold() for x in EXCLUDED|set(engine.catalog.settings['exclude'])}
    return (p.suffix.lower() in EXTENSIONS and not p.name.endswith(('.generated.h','.gen.cpp')) and
            not any(x.casefold() in excluded|{'documentation'} for x in p.parts[:-1]))


def git_tree(engine,reference):
    repo=git(engine.root,'rev-parse','--show-toplevel').decode().strip()
    prefix=Path(engine.root).relative_to(canonical(repo)).as_posix()
    prefix='' if prefix=='.' else prefix+'/'
    if reference=='INDEX':
        records=git(repo,'ls-files','-s','-z').split(b'\0');entries=[]
        for row in records:
            if not row:continue
            meta,rawname=row.split(b'\t',1);mode,oid,stage=meta.decode().split()
            if stage!='0':raise SafeError('暂存区存在未解决的合并冲突。')
            entries.append((mode,'blob',oid,rawname.decode('utf-8')))
        resolved='INDEX'
    else:
        if not re.fullmatch(r'[A-Za-z0-9_./~^{}-]{1,150}',reference) or reference.startswith('-'):
            raise SafeError('base/target必须是本地Git提交/分支；不接受命令选项。')
        resolved=git(repo,'rev-parse','--verify','--end-of-options',reference+'^{commit}').decode().strip()
        entries=[]
        for row in git(repo,'ls-tree','-r','-z',resolved).split(b'\0'):
            if not row:continue
            meta,rawname=row.split(b'\t',1);mode,kind,oid=meta.decode().split()
            entries.append((mode,kind,oid,rawname.decode('utf-8')))
    selected=[];metadata={};unavailable=[]
    for mode,kind,oid,name in entries:
        if prefix and not name.startswith(prefix):continue
        name=name[len(prefix):];valid_path(name)
        metadata[name]=mode+':'+oid
        if not source_input(engine,name):continue
        if mode not in {'100644','100755'} or kind!='blob':
            unavailable.append({'path':name,'reason':'symlink_or_submodule_not_parsed'});continue
        selected.append((name,oid))
    contents={}
    if selected:
        # One Git process for all blobs. Per-blob size is checked before copying.
        ids=''.join(oid+'\n' for _,oid in selected).encode()
        try:
            check=subprocess.run(['git','-C',repo,'cat-file','--batch-check'],input=ids,capture_output=True,timeout=60,check=False,
                                 env={**os.environ,'GIT_NO_REPLACE_OBJECTS':'1'})
            headers=[line.split() for line in check.stdout.decode().splitlines()]
            if check.returncode or len(headers)!=len(selected) or any(len(h)!=3 or h[1]!='blob' for h in headers):
                raise SafeError('Git对象尺寸校验失败。')
            sizes=[int(h[2]) for h in headers]
            if any(n>2*1024*1024 for n in sizes) or sum(sizes)>MAX_BYTES:
                raise SafeError('源码快照超过安全边界；请选择模块。')
            p=subprocess.run(['git','-C',repo,'cat-file','--batch'],input=ids,capture_output=True,timeout=120,check=False,
                             env={**os.environ,'GIT_NO_REPLACE_OBJECTS':'1','GIT_TERMINAL_PROMPT':'0'})
        except (OSError,subprocess.SubprocessError) as exc:raise SafeError('Git快照读取失败。') from exc
        if p.returncode or len(p.stdout)>MAX_BYTES:raise SafeError('源码快照读取失败或超过128MiB；请选择模块。')
        cursor=0
        for name,oid in selected:
            end=p.stdout.find(b'\n',cursor);header=p.stdout[cursor:end].decode().split()
            if len(header)!=3 or header[0]!=oid or header[1]!='blob':raise SafeError('Git对象读取校验失败。')
            size=int(header[2]);cursor=end+1
            if size>2*1024*1024:raise SafeError('单个源码文件超过2MiB安全边界。')
            contents[name]=p.stdout[cursor:cursor+size];cursor+=size+1
    return contents,metadata,resolved,unavailable


def working_tree(engine):
    files=engine.catalog.scan();contents={};meta={};unknown=[]
    for p in files:
        name=p.relative_to(engine.root).as_posix()
        if p.suffix.lower() not in EXTENSIONS:continue
        data=p.read_bytes();contents[name]=data
        oid=__import__('hashlib').sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        meta[name]=('100755' if p.stat().st_mode&0o111 else '100644')+':'+oid
    # Track even excluded/non-C++ changes without sending their content to AI.
    try:
        repo=git(engine.root,'rev-parse','--show-toplevel').decode().strip()
    except SafeError:return contents,meta,'WORKTREE',unknown
    prefix=Path(engine.root).relative_to(canonical(repo)).as_posix();prefix='' if prefix=='.' else prefix+'/'
    names=git(repo,'ls-files','--cached','--others','--exclude-standard','-z').split(b'\0')
    for raw in names:
        if not raw:continue
        name=raw.decode('utf-8')
        if prefix and not name.startswith(prefix):continue
        name=name[len(prefix):];valid_path(name);p=Path(engine.root)/name
        if name in meta or not p.exists() and not p.is_symlink():continue
        if p.is_symlink():
            data=os.readlink(p).encode();mode='120000'
            unknown.append({'path':name,'reason':'symlink_not_parsed'})
        elif p.is_file():
            if p.stat().st_size>MAX_BYTES:
                meta[name]='large:'+str(p.stat().st_size)+':'+str(p.stat().st_mtime_ns);continue
            data=p.read_bytes();mode='100755' if p.stat().st_mode&0o111 else '100644'
        else:continue
        oid=__import__('hashlib').sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();meta[name]=mode+':'+oid
    return contents,meta,'WORKTREE',unknown


def snapshot(engine,reference):
    if reference in {'WORKTREE','PLAN'}:
        data,meta,resolved,unknown=working_tree(engine)
        if reference=='PLAN':
            if not engine.plan:raise SafeError('没有待预览计划。')
            for path,old,new in engine.plan.changes:
                rel=Path(os.path.realpath(path)).relative_to(engine.root).as_posix()
                if (Path(path).read_bytes() if Path(path).exists() else None)!=old:raise SafeError('预览源码已变化。')
                if new is None:data.pop(rel,None);meta.pop(rel,None)
                else:
                    if source_input(engine,rel):data[rel]=new
                    oid=__import__('hashlib').sha1(b'blob '+str(len(new)).encode()+b'\0'+new).hexdigest();meta[rel]='100644:'+oid
            resolved='PLAN:'+engine.plan.id
    else:data,meta,resolved,unknown=git_tree(engine,reference)
    if sum(map(len,data.values()))>MAX_BYTES:raise SafeError('快照超过128MiB。')
    stamp=sha(json.dumps([{k:sha(v) for k,v in sorted(data.items())},engine.catalog.settings,engine.catalog.executable],sort_keys=True).encode())
    folder=engine.catalog.cache/'snapshots'/stamp;root=folder/'source'
    if not root.exists():
        folder.mkdir(parents=True,exist_ok=True)
        staged=Path(tempfile.mkdtemp(prefix='staging-',dir=folder))
        try:
            for name,raw in data.items():
                p=staged/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            dump_atomic(staged/'.doxygenue'/'settings.json',engine.catalog.settings)
            try: staged.rename(root)
            except OSError:
                if not root.is_dir():raise
        finally:
            if staged.exists():shutil.rmtree(staged)
    # Never trust an interrupted or externally changed content-addressed cache.
    if any(not (root/name).is_file() or (root/name).is_symlink() or (root/name).read_bytes()!=raw for name,raw in data.items()):
        raise SafeError('快照缓存内容不匹配；未使用不完整快照，请清理本项目快照缓存后重试。')
    cat=Catalog(str(root),folder/'index',engine.catalog.executable)
    if data:cat.ensure()
    return {'catalog':cat,'bytes':data,'metadata':meta,'resolved':resolved,'unavailable':unknown}


def token_text(text):
    try:
        ts,cs,ds=lex(text)
        return {'tokens':[t.value for t in ts],'directives':[d.value for d in ds]}
    except SafeError:return {'unparsed':text}


def functions(snap):
    cat=snap['catalog'];byname=defaultdict(list);spans=defaultdict(list);unresolved=[];sources={}
    for symbol in cat.symbols:
        if symbol.kind!='function':continue
        locations=[]
        for file in sorted(set(filter(None,(symbol.file,symbol.bodyfile)))):
            if file not in sources:
                try:sources[file]=Source.load(file)
                except (SafeError,UnicodeError,OSError) as exc:sources[file]=None;unresolved.append({'path':Path(file).relative_to(cat.root).as_posix(),'name':symbol.name,'reason':str(exc)})
            src=sources[file]
            if not src:continue
            matched=[]
            for o in src.occurrences:
                if o.name!=symbol.name or o.kind!='function':continue
                first=src.text.count('\n',0,o.start)+1;last=src.text.count('\n',0,o.end-1)+1
                if not ((file==symbol.file and first<=symbol.line<=last) or (file==symbol.bodyfile and o.role=='definition' and first<=symbol.bodystart<=last and last==symbol.bodyend)):continue
                matched.append(o)
            if len(matched)>1:
                unresolved.append({'path':Path(file).relative_to(cat.root).as_posix(),'name':symbol.name,'reason':'同名函数共享Doxygen行范围；无法唯一归类，保留文件级变化'})
                continue
            for o in matched:
                first=src.text.count('\n',0,o.start)+1
                rel=Path(file).relative_to(cat.root).as_posix();leading=src.leading(o)
                begin=leading[0].start if leading else o.start
                part={'path':rel,'role':o.role,'line':first,'start':o.start,'end':o.end,'raw':src.text[begin:o.end],
                      'signature':token_text(src.text[o.start:o.signature_end]),
                      'body':token_text(src.text[o.open+1:o.close]) if o.open is not None else None,
                      'comments':[clean_comment(c.value) for c in src.comments if begin<=c.start<o.end]}
                locations.append(part);spans[rel].append((begin,o.end))
        if not locations:
            unresolved.append({'name':symbol.name,'path':Path(symbol.file).relative_to(cat.root).as_posix(),'reason':'Doxygen位置不能安全归入函数'});continue
        record={'name':symbol.name,'args':symbol.args,'signature':symbol.signature,
                'documentation':symbol.documentation.get('full',{}),'locations':locations}
        phys={(x['path'],x['role'],x['start'],x['end']) for x in locations}
        existing=next((r for r in byname[symbol.name] if phys & {(x['path'],x['role'],x['start'],x['end']) for x in r['locations']}),None)
        if existing:
            seen={(x['path'],x['role'],x['start'],x['end']) for x in existing['locations']}
            existing['locations'] += [x for x in locations if (x['path'],x['role'],x['start'],x['end']) not in seen]
        else:byname[symbol.name].append(record)
    residual={}
    for path,raw in snap['bytes'].items():
        text=raw.decode('utf-8-sig');last=0;out=[]
        merged=[]
        for a,b in sorted(set(spans[path])):
            if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
            else:merged.append((a,b))
        for a,b in merged:out.append(text[last:a]);last=b
        out.append(text[last:]);residual[path]=''.join(out)
    return byname,residual,unresolved


def clean_comment(text):
    from .cpp import clean_comment as clean
    return clean(text)


def canonical_parts(r,key):
    vals=[l[key] for l in r['locations'] if l[key] is not None]
    return sorted(json.dumps(v,ensure_ascii=False,sort_keys=True) for v in vals)


def _pair(left,right):
    pairs=[];used=set();remaining=[]
    for a in left:
        candidates=[(j,b) for j,b in enumerate(right) if j not in used and a['args']==b['args']]
        if len(candidates)>1:
            ap={l['path'] for l in a['locations']}
            candidates=[(j,b) for j,b in candidates if ap & {l['path'] for l in b['locations']}]
        if len(candidates)==1:
            j,b=candidates[0];used.add(j);pairs.append((a,b))
        else:remaining.append(a)
    tail=[b for j,b in enumerate(right) if j not in used]
    # A unique name may safely expose a signature change; multiple changed
    # overloads cannot be assigned by guessing argument similarity.
    if len(remaining)==len(tail)==1 and len(left)==len(right)==1:
        pairs.append((remaining.pop(),tail.pop()))
    return pairs,remaining,tail


def compare(engine,base='HEAD',target='WORKTREE',name='',path='',detail=False,limit=50,offset=0):
    if target=='PLAN' and base=='HEAD':base='WORKTREE'
    engine.catalog.load_settings()
    before=snapshot(engine,base);after=snapshot(engine,target)
    a,ar,au=functions(before);b,br,bu=functions(after);changes=[]
    for n in sorted(set(a)|set(b)):
        pairs,removed,added=_pair(a[n],b[n])
        ambiguity=bool(removed and added and (len(a[n])>1 or len(b[n])>1))
        for old,new in pairs:
            facets=[]
            if canonical_parts(old,'signature')!=canonical_parts(new,'signature'):facets.append('signature')
            if canonical_parts(old,'body')!=canonical_parts(new,'body'):facets.append('body')
            if old['documentation']!=new['documentation'] or canonical_parts(old,'comments')!=canonical_parts(new,'comments'):facets.append('documentation')
            if sorted((l['path'],l['role']) for l in old['locations'])!=sorted((l['path'],l['role']) for l in new['locations']):facets.append('location')
            if not facets and canonical_parts(old,'raw')!=canonical_parts(new,'raw'):facets.append('format')
            if facets:changes.append((n,'modified',facets,old,new,False))
        changes += [(n,'removed',[],r,None,ambiguity) for r in removed]
        changes += [(n,'added',[],None,r,ambiguity) for r in added]
    rows=[]
    for n,change,facets,old,new,amb in changes:
        locations=(old or new)['locations']+((new or {}).get('locations',[]) if old else [])
        paths=sorted(set(l['path'] for l in locations))
        if name and name!=n and name!=n.rsplit('::',1)[-1]:continue
        if path and path not in paths:continue
        row={'name':n,'change':change,'facets':facets,'paths':paths,
             'signature':(new or old)['signature']}
        if amb:row['pairing']='unresolved_overloads'
        if change=='added' or 'signature' in facets:row['documentation_check']='required'
        elif 'body' in facets and 'documentation' not in facets:row['documentation_review']='consider_contract_changes_not_mandatory_rewrite'
        if detail:
            oldtext='\n'.join(l['path']+'\n'+l['raw'] for l in (old or {}).get('locations',[]))
            newtext='\n'.join(l['path']+'\n'+l['raw'] for l in (new or {}).get('locations',[]))
            diff='\n'.join(difflib.unified_diff(oldtext.splitlines(),newtext.splitlines(),fromfile=n+' / before',tofile=n+' / after',lineterm=''))
            row['diff']=diff[:24000];row['diff_truncated']=len(diff)>24000
        rows.append(row)
    changed_files=sorted(k for k in set(before['metadata'])|set(after['metadata']) if before['metadata'].get(k)!=after['metadata'].get(k))
    unclassified=[]
    for f in changed_files:
        if path and f!=path:continue
        left,right=ar.get(f,''),br.get(f,'')
        try:
            lt,lc,ld=lex(left);rt,rc,rd=lex(right)
            residual_changed=([t.value for t in lt],[c.value for c in lc],[d.value for d in ld])!=([t.value for t in rt],[c.value for c in rc],[d.value for d in rd])
        except SafeError:residual_changed=left!=right
        mode_changed=(before['metadata'].get(f,'').split(':')[0]!=after['metadata'].get(f,'').split(':')[0])
        if f not in ar and f not in br or residual_changed or left!=right or mode_changed:
            item={'path':f,'reason':'outside_function_or_unparsed' if f in ar or f in br else 'non_source_or_excluded'}
            if f in ar or f in br:
                if not residual_changed and left!=right and not mode_changed:item['reason']='outside_function_format_only'
                elif mode_changed and not residual_changed:item['reason']='file_mode_or_existence_changed'
            if detail and (left or right):
                diff='\n'.join(difflib.unified_diff(left.splitlines(),right.splitlines(),fromfile=f+' / before',tofile=f+' / after',lineterm=''))
                item['diff']=diff[:12000];item['diff_truncated']=len(diff)>12000
            unclassified.append(item)
    report={'base':before['resolved'],'target':after['resolved'],'functions':rows[offset:offset+limit],
            'total_functions':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None,
            'unclassified':unclassified[:limit],'unclassified_total':len(unclassified),
            'unresolved':(au+bu+before['unavailable']+after['unavailable'])[:limit],
            'unresolved_total':len(au+bu+before['unavailable']+after['unavailable']),
            'changed_files':len(changed_files),
            'basis':'Git原始字节+双侧Doxygen索引+函数范围复核；不是编译器级重构证明'}
    # Complete local report is available even when the compact MCP page is bounded.
    folder=engine.catalog.cache/'change-reports';folder.mkdir(exist_ok=True)
    full={**report,'functions':rows,'unclassified':unclassified,'unresolved':au+bu+before['unavailable']+after['unavailable']}
    output=folder/(sha(json.dumps(full,ensure_ascii=False,sort_keys=True).encode())[:20]+'.json')
    dump_atomic(output,full);report['report']=str(output)
    return report
