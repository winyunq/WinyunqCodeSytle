"""Bounded inventory across source, content and configuration, with UE module evidence."""
from __future__ import annotations
from collections import Counter
import re
from .common import *

def inventory(root,bindings,limit=30,offset=0):
    types=Counter();items=[];modules=[];descriptors=[]
    for p in files(root):
        rel=p.relative_to(root).as_posix();suffix=p.suffix.lower()
        if suffix in ('.h','.hpp','.cpp','.inl','.cc','.cxx'):kind='code'
        elif suffix in ('.uasset','.umap'):kind='ue_asset'
        elif suffix in ('.json','.csv','.ini','.db','.sqlite','.sqlite3'):kind='data_or_config'
        elif p.name.endswith(('.Build.cs','.Target.cs')):kind='ue_build'
        elif suffix in ('.uproject','.uplugin'):kind='ue_descriptor'
        else:kind='other'
        types[kind]+=1
        if kind!='other':items.append({'path':rel,'kind':kind})
        if kind=='ue_descriptor':
            try:
                d=json_load(read_bytes(p).decode('utf-8-sig'))
                descriptors.append({'path':rel,**{k:d[k] for k in ('EngineAssociation','Modules','Plugins') if k in d}})
            except (ValueError,OSError,SafeError):descriptors.append({'path':rel,'error':'unparsed'})
        if p.name.endswith('.Build.cs'):
            text=read_bytes(p).decode('utf-8-sig');entry={'name':p.name[:-9],'path':rel}
            for key in ('PublicDependencyModuleNames','PrivateDependencyModuleNames'):
                chunks=re.findall(re.escape(key)+r'\.AddRange\s*\((.*?)\)\s*;',text,re.S)
                entry[key]=list(dict.fromkeys(x for c in chunks for x in re.findall(r'"([^"\n]+)"',c)))
            entry['evidence']='literal_AddRange_only; computed C# dependencies are not evaluated'
            modules.append(entry)
    return {'counts':dict(types),'descriptors':descriptors[:limit],'modules':modules[:limit],'descriptor_count':len(descriptors),'module_count':len(modules),
            'data_bindings':[{'name':b['name'],'path':b['path'],'format':b.get('format','json'),'brief':b.get('brief','')} for b in bindings.values()],
            'files':items[offset:offset+limit],'total':len(items),'next_offset':offset+limit if offset+limit<len(items) else None,
            'unsupported_writes':['arbitrary uasset/Blueprint graphs','Build.cs/Target.cs','INI duplicate-key semantics','SQLite/SQL servers','binary map extraction']}

def usage(root,term,limit=5):
    """Textual evidence, not a semantic call graph. Return locations, not whole files."""
    if not term:return []
    result=[]
    for p in files(root):
        if p.suffix.lower() not in {'.h','.hpp','.cpp','.cs','.ini','.json','.csv'}:continue
        if p.stat().st_size>MAX_FILE:continue
        try:text=read_bytes(p).decode('utf-8-sig')
        except (ValueError,OSError):continue
        for i,line in enumerate(text.splitlines(),1):
            if term in line:
                result.append({'path':p.relative_to(root).as_posix(),'line':i,'text':line.strip()[:240]})
                if len(result)>=limit:return result
    return result


def ue_specifiers(text,line,leaf):
    from doxygenue.cpp import lex
    lines=text.splitlines(keepends=True)
    upto=''.join(lines[:line+2]);start=max(0,len(''.join(lines[:max(0,line-20)])))
    chunk=upto[start:];ts,_,_=lex(chunk)
    candidates=[]
    for i,t in enumerate(ts):
        if t.value!='UFUNCTION' or i+1>=len(ts) or ts[i+1].value!='(':continue
        depth=0
        for j in range(i+1,len(ts)):
            if ts[j].value=='(':depth+=1
            elif ts[j].value==')':depth-=1
            if depth==0:
                tail=ts[j+1:]
                # At most the subsequent declaration; never borrow an older annotation.
                names=[]
                for x in tail:
                    if x.value in (';','{','}'):break
                    names.append(x.value)
                if leaf in names:candidates.append(re.sub(r'\s+',' ',chunk[ts[i+1].end:ts[j].start]).strip())
                break
    return candidates[-1] if candidates else ''
