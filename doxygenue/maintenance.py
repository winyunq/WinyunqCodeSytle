"""Cpp-first native member maintenance using Doxygen identity + source offsets.

No whole-file payload. One supplied function drives its implementation and its
header declaration. Existing comments/UE metadata/default args are preserved.
Multi-file writes use the shared Plan (locks, revision checks, rollback journal).
"""
from __future__ import annotations
from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import re
import textwrap
from types import SimpleNamespace

from .cpp import Source, SafeError, canonical, inside, lex, pairs, HEADERS, IDENT, ANNOTATIONS, EXCLUDED


@dataclass
class Signature:
    source: Source
    occurrence: object
    start: int
    name_start: int
    left: int
    right: int
    signature_end: int
    leaf: str

    @property
    def prefix(self):
        return self.source.text[self.start:self.name_start].strip()

    @property
    def params(self):
        return self.source.text[self.left+1:self.right]

    @property
    def suffix(self):
        return self.source.text[self.right+1:self.signature_end].strip().rstrip(";").strip()


def signature(source, occurrence):
    ts = [t for t in source.tokens if occurrence.start <= t.start < occurrence.signature_end]
    pm = pairs(ts)
    leaf = occurrence.name.rsplit("::", 1)[-1]
    hits = [i for i in range(len(ts)-1) if ts[i].value == leaf.lstrip("~") and ts[i+1].value == "("]
    if len(hits) != 1:
        raise SafeError("不能唯一确认函数签名；不会猜测生成头文件。")
    i = hits[0]
    j = i - 1 if leaf.startswith("~") else i
    while j >= 2 and ts[j-1].value == "::":
        j -= 2
    return Signature(source, occurrence, occurrence.start, ts[j].start, ts[i+1].start,
                     ts[pm[i+1]].start, occurrence.signature_end, leaf)


def newline(source):
    return "\r\n" if "\r\n" in source.text else "\n"


def normalized(text, source, at=0):
    lines = textwrap.dedent(text).strip().splitlines()
    if not lines:
        return ""
    indent = re.match(r"[ \t]*", source.text[source.text.rfind("\n", 0, at)+1:at]).group()
    return lines[0] + "".join(newline(source) + indent + line for line in lines[1:])


def merge_tokens(source, start, end, wanted):
    """Apply token diffs within the selected function, preserving outside bytes."""
    old = sorted((t for t in source.tokens + source.directives if start <= t.start and t.end <= end), key=lambda t: t.start)
    new, comments, directives = lex(wanted)
    if comments:
        raise SafeError("完整函数载荷仅提交代码；注释使用独立操作。")
    new = sorted(new + directives, key=lambda t: t.start)
    matcher = difflib.SequenceMatcher(None, [t.value for t in old], [t.value for t in new], autojunk=False)
    splices = []
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == "equal":
            continue
        x = old[a].start if a < len(old) else (old[-1].end if old else start)
        y = old[b-1].end if b > a else x
        replacement = normalized(wanted[new[c].start:new[d-1].end], source, x) if c < d else ""
        if tag == "insert":
            # Whitespace ensures new and old tokens cannot accidentally fuse.
            replacement = " " + replacement + " "
        splices.append((x, y, replacement))
    text = source.text
    for x, y, replacement in reversed(splices):
        text = text[:x] + replacement + text[y:]
    check_tokens, cs, ds = lex(text)
    all_tokens = sorted(source.tokens + source.directives, key=lambda t: t.start)
    expected = [t.value for t in all_tokens if t.end <= start] + [t.value for t in new] + [t.value for t in all_tokens if t.start >= end]
    if [t.value for t in sorted(check_tokens + ds, key=lambda t: t.start)] != expected:
        raise SafeError("合并产生 token 粘连；扩大本次编辑到完整表达式。")
    return text


def split_params(text):
    ts, cs, ds = lex(text)
    if cs or ds:
        raise SafeError("参数中的注释/宏指令不能自动重排。")
    depth = angle = 0
    spans, begin = [], 0
    for t in ts:
        v = t.value
        if v in {"(", "[", "{"}: depth += 1
        elif v in {")", "]", "}"}: depth -= 1
        elif v == "<": angle += 1
        elif v == ">": angle = max(0, angle-1)
        elif v == ">>": angle = max(0, angle-2)
        elif v == "," and depth == angle == 0:
            spans.append(text[begin:t.start].strip());begin = t.end
    if text[begin:].strip(): spans.append(text[begin:].strip())
    return spans


def param_core(text):
    ts, _, _ = lex(text)
    i = 0
    pm = pairs(ts)
    while i+1 < len(ts) and ts[i].value == "UPARAM" and ts[i+1].value == "(":
        i = pm[i+1]+1
    level = 0
    for j in range(i, len(ts)):
        if ts[j].value in {"(", "[", "{"}: level += 1
        elif ts[j].value in {")", "]", "}"}: level -= 1
        elif ts[j].value == "=" and level == 0:
            ts = ts[:j];break
    return [t.value for t in ts[i:]]


def header_declaration(new_signature, old_source=None, old_occurrence=None, reflection=""):
    """Retain existing declaration-only metadata and default args by identity."""
    prefix = new_signature.prefix
    suffix = new_signature.suffix
    if any(t.value in {"virtual", "static", "override", "final"} for t in lex(prefix + " " + suffix)[0]):
        raise SafeError(".cpp 定义不携带 virtual/static/override/final；已有声明属性由程序保留。")
    params = split_params(new_signature.params)
    for param in params:
        if "=" in [t.value for t in lex(param)[0]]:
            raise SafeError(".cpp 参数不添加默认值；已有默认值由头文件保留。")
    preserved_prefix = ""
    preserved_suffix = ""
    if old_occurrence is not None:
        old = signature(old_source, old_occurrence)
        ots, _, _ = lex(old.prefix)
        pm = pairs(ots)
        i = 0
        while i < len(ots):
            if ots[i].value in ANNOTATIONS and i+1 < len(ots) and ots[i+1].value == "(":
                i = pm[i+1]+1
            elif ots[i].value in {"virtual", "static", "inline", "explicit", "friend"} or ots[i].value.endswith("_API"):
                i += 1
            elif ots[i].value == "[":
                i = pm[i]+1
            else:
                break
        if i:
            end = ots[i].start if i < len(ots) else len(old.prefix)
            preserved_prefix = old.prefix[:end]
        old_params = split_params(old.params)
        def preserve_parameter(p):
            exact=next((x for x in old_params if param_core(x)==param_core(p)),None)
            if exact is not None:return exact
            core=param_core(p)
            if len(core)<2 or not IDENT.fullmatch(core[-1]):return p
            previous=next((x for x in old_params if param_core(x) and param_core(x)[-1]==core[-1]),None)
            if previous is None:return p
            # A .cpp type edit must not silently remove a header default/UPARAM.
            # If a retained default becomes ill-typed, configured compilation
            # rejects the transaction instead of "repairing" the API by omission.
            pts,_,_=lex(previous);depth=0;default=""
            for t in pts:
                if t.value in {"(","[","{"}:depth+=1
                elif t.value in {")","]","}"}:depth-=1
                elif t.value=="=" and depth==0:default=previous[t.start:];break
            annotation=""
            if len(pts)>1 and pts[0].value=="UPARAM" and pts[1].value=="(":
                annotation=previous[:pts[pairs(pts)[1]].end]+" "
            return annotation+p+(" "+default if default else "")
        params = [preserve_parameter(p) for p in params]
        old_tail = old.suffix
        attributes = re.findall(r"\b(?:override|final)\b", old_tail)
        preserved_suffix = " " + " ".join(attributes) if attributes else ""
        if re.search(r"=\s*0\s*$", old_tail):
            preserved_suffix += " = 0"
        # Do not silently keep a dangling default after a newly added required arg.
        seen_default = False
        for p in params:
            has_default = "=" in [t.value for t in lex(p)[0]]
            if seen_default and not has_default:
                raise SafeError("新增必需参数位于已有默认参数之后；调整.cpp参数顺序，不能静默删除默认值。")
            seen_default |= has_default
    if reflection and old_occurrence is not None:
        old_tokens = lex(preserved_prefix)[0]
        if old_tokens and old_tokens[0].value == "UFUNCTION":
            close = pairs(old_tokens)[1]
            if [t.value for t in old_tokens[:close + 1]] != [t.value for t in lex(reflection)[0]]:
                raise SafeError("已有 UFUNCTION 标记与载荷不一致；修改标记使用现有 modify_member 操作。")
            reflection = ""
    return ((reflection + "\n" if reflection else "") + preserved_prefix + prefix + (" " if prefix else "") + new_signature.leaf + "(" + ", ".join(params) + ")"
            + (" " + suffix if suffix else "") + preserved_suffix + ";")


def class_location(engine, owner, catalog=None):
    catalog = catalog or engine.catalog
    choices = {(c["file"], c["line"]): c for c in catalog.compounds
               if c["name"] == owner and c["kind"] in {"class", "struct"} and Path(c["file"]).suffix.lower() in HEADERS}
    if len(choices) != 1:
        raise SafeError("Doxygen 未发现唯一所属类头文件；不猜测 .h。名称空间自由函数请使用明确声明维护。")
    c = next(iter(choices.values()))
    source = Source.load(c["file"])
    containers = [x for x in source.containers if x.name == owner and
                  source.text.count("\n", 0, x.start)+1 <= c["line"] <= source.text.count("\n", 0, x.close)+1]
    if len(containers) != 1 or containers[0].templated:
        raise SafeError("所属类范围不明确/为类模板；本版本不猜测生成类模板的跨文件声明。")
    return source, containers[0]


def insert_member(source, container, declaration, access):
    if access not in {"public", "protected", "private"}:
        raise SafeError("access 必须为 public/protected/private。")
    ts = source.tokens;pm = pairs(ts)
    sections=[];i=next(i for i,t in enumerate(ts) if t.start==container.open)+1
    while i < len(ts) and ts[i].start < container.close:
        if ts[i].value in {"public","protected","private"} and i+1 < len(ts) and ts[i+1].value==":":
            sections.append((ts[i].value,ts[i].start,ts[i+1].end));i+=2;continue
        if ts[i].value in {"(","[","{"}:
            i=pm[i]+1
        else:i+=1
    chosen=[(k,x) for k,x in enumerate(sections) if x[0]==access]
    if chosen:
        k,section=chosen[-1]
        at=sections[k+1][1] if k+1<len(sections) else container.close
        label=""
    else:
        at=container.close;label=access+":"+newline(source)
    # Determine indentation from existing members, then the containing class.
    members=[o for o in source.occurrences if container.open<o.start<container.close and o.name.rpartition("::")[0]==container.name]
    if members:
        indent=re.match(r"[ \t]*",source.text[source.text.rfind("\n",0,members[0].start)+1:members[0].start]).group()
        indent=indent or "    "
    else:
        base=re.match(r"[ \t]*",source.text[source.text.rfind("\n",0,container.start)+1:container.start]).group()
        indent=base+"    "
    # Insert before whole line if the next label/brace has only indentation.
    line=source.text.rfind("\n",0,at)+1
    if not source.text[line:at].strip():at=line
    addition=newline(source)+label+newline(source).join(indent+line for line in declaration.splitlines())+newline(source)
    return source.text[:at]+addition+source.text[at:]


def include_spec(value):
    value=value.strip()
    if value.startswith("#include"):
        value=value[len("#include"):].strip()
    if not value or any(c in value for c in "\r\n\0#;$"):
        raise SafeError("include 仅接受一个头文件名，不接受指令注入。")
    if value.startswith("<") and value.endswith(">"):
        inner=value[1:-1]
        if any(c in inner for c in '<>"'):raise SafeError("无效头文件名。")
        return "<"+inner+">"
    inner=value[1:-1] if value.startswith('"') and value.endswith('"') else value
    if any(c in inner for c in '<>"'):raise SafeError("无效头文件名。")
    return '"'+inner.replace('\\','/')+'"'


def with_includes(path, raw, includes):
    source=Source.load(path,raw or b"")
    existing=[];depth=0;directives=[]
    header_guard = False
    if Path(path).suffix.lower() in HEADERS and len(source.directives)>1:
        a=re.fullmatch(r"#\s*ifndef\s+(\w+)\s*",source.directives[0].value)
        b=re.fullmatch(r"#\s*define\s+(\w+)\s*",source.directives[1].value)
        header_guard=bool(a and b and a.group(1)==b.group(1))
    for d in source.directives:
        key=re.match(r"#\s*(\w+)",d.value).group(1)
        if key in {"if","ifdef","ifndef"}:depth+=1
        elif key=="endif":depth-=1
        elif key=="include" and depth <= bool(header_guard):
            m=re.match(r'#\s*include\s*([<"][^>"\r\n]+[>"])',d.value)
            if m:existing.append(m.group(1));directives.append(d)
    additions=[]
    for inc in includes:
        value=include_spec(inc)
        if value not in existing+additions:additions.append(value)
    if not additions:return raw if raw is not None else b"",False
    first_code=source.tokens[0].start if source.tokens else len(source.text)
    early=[d for d in directives if d.start<first_code]
    generated=next((d for d in early if '.generated.h"' in d.value),None)
    if generated:at=source.text.rfind("\n",0,generated.start)+1
    elif early:
        e=early[-1].end;at=source.text.find("\n",e);at=len(source.text) if at<0 else at+1
    else:
        headers=source.file_header()
        at=headers[-1].end if headers else 0
        for index,d in enumerate(source.directives):
            if d.start>=first_code:break
            if re.fullmatch(r"#\s*pragma\s+once\s*",d.value) or header_guard and index==1:
                at=d.end
        if at:
            e=source.text.find("\n",at);at=len(source.text) if e<0 else e+1
    nl=newline(source)
    fragment=(nl if at and not source.text[:at].endswith("\n") else "")+"".join("#include "+v+nl for v in additions)
    text=source.text[:at]+fragment+source.text[at:]
    check=Source.load(path,source.encode(text))
    if [t.value for t in check.tokens]!=[t.value for t in source.tokens] or [t.value for t in check.comments]!=[t.value for t in source.comments]:
        raise SafeError("include 写入影响代码或注释。")
    return source.encode(text),True


def source_path(engine,path,name="",allow_new=False,catalog=None):
    catalog = catalog or engine.catalog
    if not path:
        s=engine._resolve_symbol(name)
        path=s.bodyfile or s.file
    p=canonical(Path(engine.root)/path)
    if not inside(p,engine.scope) or Path(p).suffix.lower() not in {".cpp",".cc",".cxx",".h",".hpp",".hh",".inl"}:
        raise SafeError("path 需要指向 scope 内的 C++ 文件。")
    if Path(p).exists() and p not in catalog.hashes:
        raise SafeError("文件不在 Doxygen 索引内；不绕过排除/隐藏范围。")
    if not Path(p).exists() and not allow_new:raise SafeError("文件不存在。")
    return p


def maintain_includes(engine,path,name,includes):
    engine.catalog.ensure()
    if not includes:raise SafeError("提供 includes 数组或一个头文件名。")
    p=source_path(engine,path,name)
    old=Path(p).read_bytes();new,changed=with_includes(p,old,includes)
    if not changed:return {"status":"unchanged","files":[]}
    result=engine._plan("Write","include",None,[(p,old,new)],{})
    engine.plan.locks=[("",p,True)]
    result["locked"]=bool(engine.store.blocked("",p,all_file=True))
    return result


def _function_module_root(engine, path):
    if not path:
        return None
    raw_target=Path(engine.root)/path
    try:
        relative=raw_target.relative_to(engine.root)
    except ValueError:
        raise SafeError("function 操作需要 scope 内已存在的 .cpp 路径。")
    current=Path(engine.root)
    for part in relative.parts:
        if part in {".",".."}:
            raise SafeError("function 路径不能包含父目录跳转。")
        current=current/part
        if current.is_symlink():
            raise SafeError("function 路径不能经过符号链接。")
    target = canonical(raw_target)
    if (not inside(target, engine.scope) or not Path(target).is_file()
            or Path(target).suffix.lower() not in {".cpp", ".cc", ".cxx"}):
        raise SafeError("function 操作需要 scope 内已存在的 .cpp 路径。")
    parts = Path(target).relative_to(engine.root).parts
    source_index = next((i for i, part in enumerate(parts) if part.casefold() == "source"), None)
    if source_index is None or source_index + 1 >= len(parts):
        return None
    module_root = canonical(Path(engine.root).joinpath(*parts[:source_index + 2]))
    if not inside(module_root, engine.scope):
        raise SafeError("function 操作的 scope 必须包含所属 Unreal 模块。")
    return module_root


def _quick_function_catalog(engine,path,content,name,module_root):
    target=canonical(Path(engine.root)/path)
    module_root=Path(module_root)
    settings=engine.catalog.settings
    excluded={x.casefold() for x in EXCLUDED | set(settings.get("exclude",[]))}
    excluded.add("documentation")
    if any(part.casefold() in excluded for part in Path(target).relative_to(engine.root).parts):
        raise SafeError("function 路径位于当前排除范围内。")
    if Path(target).name.endswith((".generated.h",".gen.cpp")):
        raise SafeError("function 路径不是可维护的普通源码文件。")
    if Path(target).stat().st_size>2*1024*1024:
        raise SafeError("源码超过 2 MiB 安全上限；请缩小操作范围。")

    fragment=Source.load(str(Path(target).parent/"__function_payload.cpp"),content.encode())
    definitions=[o for o in fragment.occurrences if o.role=="definition" and o.kind=="function"]
    if len(definitions)!=1:
        raise SafeError("一次提交一个范围可复核的函数定义，不是整个文件；不会删除未提交函数。")
    fullname=definitions[0].name
    if name and name not in {fullname,fullname.rsplit("::",1)[-1]}:
        raise SafeError("name 与 .cpp 函数定义不一致；本操作不执行重命名。")
    owner=fullname.rpartition("::")[0]
    if not owner:
        raise SafeError("Cpp-first 自动 .h 同步需要 Class::Member；自由函数请使用 add_symbol 或普通代码编辑。")

    cpp=Source.load(target)
    owner_leaf=owner.rsplit("::",1)[-1]
    header_stems={owner_leaf.casefold(),Path(target).stem.casefold()}
    if len(owner_leaf)>1 and owner_leaf[0] in "UAFI":
        header_stems.add(owner_leaf[1:].casefold())
    roots=[Path(target).parent,module_root/"Public",module_root/"Private",
           module_root/"Internal",module_root/"Classes",module_root]
    includes=[]
    for directive in cpp.directives:
        match=re.match(r'#\s*include\s*"([^"\r\n]+)"',directive.value)
        if match and Path(match.group(1)).stem.casefold() in header_stems:
            includes.append(match.group(1))
    candidates=set()
    for include in includes:
        for root in roots:
            raw_candidate=root/include
            candidate=canonical(raw_candidate)
            if (not raw_candidate.is_symlink() and inside(candidate,module_root)
                    and Path(candidate).is_file() and Path(candidate).suffix.lower() in HEADERS
                    and Path(candidate).stat().st_size<=2*1024*1024):
                candidates.add(candidate)
    headers=[]
    for candidate in sorted(candidates):
        source=Source.load(candidate)
        containers=[item for item in source.containers if item.name==owner]
        if len(containers)==1 and not containers[0].templated:
            headers.append((source,containers[0]))
    if len(headers)!=1:
        raise SafeError("无法从指定 .cpp 的所属类头文件中唯一定位声明；不扫描全项目或猜测头文件。")
    header,container=headers[0]
    line=header.text.count("\n",0,container.start)+1
    compounds=[{"file":header.path,"line":line,"name":owner,"kind":"class"}]

    occurrences=[o for o in cpp.occurrences if o.name==fullname and o.role=="definition"]
    declarations=[o for o in header.occurrences if o.name==fullname]
    symbols=[]
    if occurrences or declarations:
        symbols=[SimpleNamespace(name=fullname,file=header.path,
            bodyfile=target if occurrences else "",kind="function",
            signature="",brief="")]
    return SimpleNamespace(settings=settings,compounds=compounds,symbols=symbols,
        hashes={target:"",header.path:""},ensure=lambda *args,**kwargs:None)


def maintain_function(engine,path,content,name,includes,access,add_only=False):
    module_root = _function_module_root(engine, path)
    if module_root:
        catalog=_quick_function_catalog(engine,path,content,name,module_root)
        return _maintain_function_indexed(engine,path,content,name,includes,access,add_only,catalog)
    return _maintain_function_indexed(engine,path,content,name,includes,access,add_only)


def _maintain_function_indexed(engine,path,content,name,includes,access,add_only=False,catalog=None):
    catalog = catalog or engine.catalog
    catalog.ensure()
    ts,cs,ds=lex(content)
    if cs:raise SafeError("只提交 .cpp 代码；已有注释由程序保留，新增说明独立写。")
    leading_includes=[d for d in ds if ts and d.start < ts[0].start and re.match(r"#\s*include\b",d.value)]
    inferred=[re.sub(r"^#\s*include\s*","",d.value) for d in leading_includes]
    for d in reversed(leading_includes):content=content[:d.start]+"".join("\n" if c=="\n" else " " for c in d.value)+content[d.end:]
    tokens = lex(content)[0]
    reflection = ""
    if len(tokens) > 1 and tokens[0].value == "UFUNCTION" and tokens[1].value == "(":
        close = pairs(tokens)[1]
        reflection = content[tokens[0].start:tokens[close].end]
        content = content[tokens[close].end:]
        tokens = lex(content)[0]
        if tokens and tokens[0].value == "UFUNCTION":
            raise SafeError("一个函数只能携带一个 UFUNCTION 标记。")
    fragment=Source.load(str(Path(engine.root)/"__payload.cpp"),content.encode())
    definitions=[o for o in fragment.occurrences if o.role=="definition" and o.kind=="function"]
    if len(definitions)!=1 or len(fragment.occurrences)!=1 or not ts:
        raise SafeError("一次提交一个范围可复核的函数定义，不是整个文件；不会删除未提交函数。")
    o=definitions[0]
    if fragment.tokens[0].start!=o.start or fragment.tokens[-1].end!=o.end:
        raise SafeError("载荷必须是一个完整函数，不能夹带类/命名空间/变量。")
    fullname=o.name
    if name and name not in {fullname,fullname.rsplit("::",1)[-1]}:
        raise SafeError("name 与 .cpp 函数定义不一致；本操作不执行重命名。")
    owner,_,leaf=fullname.rpartition("::")
    if not owner:raise SafeError("Cpp-first 自动 .h 同步需要 Class::Member；自由函数可用 add_symbol 或普通代码编辑。")
    header,container=class_location(engine,owner,catalog)
    sig=signature(fragment,o)
    existing=[s for s in catalog.symbols if s.name==fullname]
    if len(existing)>1:raise SafeError("同名重载不能唯一定位；拒绝猜测头文件签名。")
    if add_only and existing and existing[0].bodyfile:raise SafeError("函数已存在；使用 operation=function 编辑而不是 add_symbol。")
    header_original=header.raw
    old_decl=[x for x in header.occurrences if x.name==fullname]
    htext=header.text
    if len(old_decl)>1:
        declarations=[[t.value for t in header.tokens if item.start<=t.start and t.end<=item.end] for item in old_decl]
        if any(values!=declarations[0] for values in declarations[1:]):
            raise SafeError("头文件有重载声明；不猜测要更新的签名。")
        duplicate_lines=[]
        for item in old_decl[1:]:
            if header.leading(item):
                raise SafeError("重复声明带有独立注释；拒绝隐式删除。")
            line_start=header.text.rfind("\n",0,item.start)+1
            line_end=header.text.find("\n",item.end)
            if line_end<0:line_end=len(header.text)
            if (header.text[line_start:item.start].strip() or header.text[item.end:line_end].strip()
                    or any(line_start<=comment.start<line_end for comment in header.comments)):
                raise SafeError("重复声明不是独立源码行；拒绝删除。")
            previous_lines=header.text[:line_start].splitlines()
            previous=next((line.strip() for line in reversed(previous_lines) if line.strip()),"")
            if previous.startswith("//") or re.match(r"(?:UFUNCTION|UPROPERTY)\s*\(",previous):
                raise SafeError("重复声明前有注释或反射标记；拒绝隐式删除。")
            duplicate_lines.append((line_start,line_end+1 if line_end<len(header.text) else line_end))
        for start,end in sorted(duplicate_lines,reverse=True):
            htext=htext[:start]+htext[end:]
        header=Source.load(header.path,header.encode(htext))
        containers=[item for item in header.containers if item.name==owner and item.kind in {"class","struct"}]
        if len(containers)!=1 or containers[0].templated:
            raise SafeError("清理重复声明后所属类范围不明确。")
        container=containers[0]
        old_decl=[x for x in header.occurrences if x.name==fullname]
        if len(old_decl)!=1:raise SafeError("重复声明清理后仍不能唯一定位。")
    decl=old_decl[0] if old_decl else None
    if decl and decl.role=="definition":raise SafeError("成员已在头文件内联定义；直接编辑其函数体，不隐式迁移到.cpp。")
    if not path:
        if existing and existing[0].bodyfile:path=existing[0].bodyfile
        else:
            implementations={s.bodyfile for s in catalog.symbols if s.name.rpartition("::")[0]==owner and s.bodyfile and Path(s.bodyfile).suffix.lower() not in HEADERS}
            if len(implementations)==1:path=next(iter(implementations))
            elif len(implementations)>1:raise SafeError("所属类分布多个.cpp，首次增加成员请提供 path。")
            else:
                hp=Path(header.path);parts=list(hp.parts)
                if "Public" in parts:
                    parts[parts.index("Public")]="Private";path=str(Path(*parts).with_suffix(".cpp"))
                else:path=str(hp.with_suffix(".cpp"))
    p=source_path(engine,path,allow_new=True,catalog=catalog)
    if Path(p).suffix.lower() in HEADERS:raise SafeError("本操作提交.cpp实现；头文件由程序同步。")
    if existing and existing[0].bodyfile and canonical(existing[0].bodyfile)!=p:raise SafeError("函数已在另一个.cpp定义；不隐式移动或制造重复定义。")
    original=Path(p).read_bytes() if Path(p).exists() else None
    cpp=Source.load(p,original or b"")
    old_defs=[x for x in cpp.occurrences if x.name==fullname and x.role=="definition"]
    if len(old_defs)>1:raise SafeError(".cpp 有重复/条件分支定义；拒绝猜测。")
    if existing and existing[0].bodyfile and not old_defs:raise SafeError("Doxygen 定义不能映射到.cpp范围。")
    declaration=header_declaration(sig,header,decl,reflection)
    if decl:
        new_decl=normalized(declaration,header,decl.start)
        if [t.value for t in lex(header.text[decl.start:decl.end])[0]] != [t.value for t in lex(new_decl)[0]]:
            htext=header.text[:decl.start]+new_decl+header.text[decl.end:]
    else:
        htext=insert_member(header,container,declaration,access)
    if old_defs:
        old_o=old_defs[0]
        new_body=fragment.text[o.open+1:o.close]
        # This is a replacement operation: removing expression tokens is legal.
        if not lex(new_body)[0]:raise SafeError("不能把现有函数清空；明确删除函数体请用 Delete。")
        text=merge_tokens(cpp,old_o.open+1,old_o.close,new_body)
        interim=Source.load(p,cpp.encode(text));old_o2=next(x for x in interim.occurrences if x.name==fullname)
        new_sig=fragment.text[o.start:o.open].strip()
        text=merge_tokens(interim,old_o2.start,old_o2.signature_end,new_sig)
    else:
        # Do not append inside an unterminated conditional or namespace.
        text=cpp.text+newline(cpp)+content.strip().replace("\r\n","\n").replace("\n",newline(cpp))+newline(cpp)
    cpraw=cpp.encode(text)
    incs=list(includes)+inferred
    existing_includes=[d.value for d in cpp.directives if re.match(r"#\s*include\b",d.value)]
    header_name = Path(header.path).name.casefold()
    if not any(header_name in d.casefold() for d in existing_includes):
        incs.insert(0,os.path.relpath(header.path,Path(p).parent).replace(os.sep,"/"))
    cpraw,inc_changed=with_includes(p,cpraw,incs)
    hpraw=header.encode(htext)
    ch=Source.load(header.path,hpraw);cc=Source.load(p,cpraw)
    declarations=[x for x in ch.occurrences if x.name==fullname];implementations=[x for x in cc.occurrences if x.name==fullname]
    if len(declarations)!=1 or len(implementations)!=1 or declarations[0].args!=implementations[0].args:
        raise SafeError("自动同步后声明/定义未能唯一配对；拒绝提交。")
    def others(src):
        return [(x.name,src.text[x.start:x.end]) for x in src.occurrences if x.name!=fullname]
    if others(header)!=others(ch) or others(cpp)!=others(cc):raise SafeError("自动同步影响了兄弟对象。")
    def outside_comments(src,definitions):
        return [x.value for x in src.comments if not any(d.start<=x.start and x.end<=d.end for d in definitions)]
    if [x.value for x in header.comments]!=[x.value for x in ch.comments] or outside_comments(cpp,old_defs)!=outside_comments(cc,implementations):
        raise SafeError("自动同步改变了函数范围外的注释。")
    changes=[]
    if hpraw!=header_original:changes.append((header.path,header_original,hpraw))
    if cpraw!=original:changes.append((p,original,cpraw))
    if not changes:return {"status":"unchanged","files":[]}
    result=engine._plan("Write","function",existing[0] if existing else None,changes,{header.path:header_original,p:original})
    engine.plan.locks=[(fullname,header.path,False),(fullname,p,inc_changed),(owner,header.path,False)]
    result["locked"]=any(engine.store.blocked(n,f,all_file=allfile) for n,f,allfile in engine.plan.locks)
    result["header_synced"]=os.path.relpath(header.path,engine.root)
    result["function"]=fullname
    if hpraw!=header_original:
        result["documentation_review"]="签名/接口改变；保留既有说明，使用 check_comments 检查参数文档。"
    # Suggestions are diagnostic, not mandatory IDs/permission handshakes.
    if not existing:
        from .search import rank
        matches=rank(catalog.symbols,leaf,catalog.settings["aliases"],engine.scope,"")[:3]
        result["reuse_candidates"]=[{"name":s.name,"brief":s.brief} for s,_,_,_ in matches]
    return result


def edit_include(engine,path,name,old_include,new_include,delete=False,reason=""):
    engine.catalog.ensure()
    p=source_path(engine,path,name)
    source=Source.load(p)
    wanted=include_spec(old_include)
    matches=[]
    for d in source.directives:
        m=re.match(r'#\s*include\s*([<"][^>"\r\n]+[>"])',d.value)
        if m and m.group(1)==wanted:matches.append((d,m))
    if len(matches)!=1:raise SafeError("include 未找到或不唯一；不猜测条件分支。")
    d,m=matches[0]
    if delete:
        if not reason.strip():raise SafeError("独立删除需要具体理由。")
        a,b=d.start,d.start+m.end()
        replacement=""
    else:
        a,b=d.start+m.start(1),d.start+m.end(1)
        replacement=include_spec(new_include)
    text=source.text[:a]+replacement+source.text[b:]
    if [t.value for t in lex(text)[0]]!=[t.value for t in source.tokens]:raise SafeError("include 操作影响了源码 token。")
    result=engine._plan("Delete" if delete else "Write","include",None,[(p,source.raw,source.encode(text))],{},reason=reason)
    engine.plan.locks=[("",p,True)]
    result["locked"]=bool(engine.store.blocked("",p,all_file=True))
    return result


def try_signature_edit(engine,symbol,old_code,new_code,path="",part=""):
    """A normal short edit hitting a signature automatically synchronizes .h.

    Returns None for a body edit. No preliminary Read/Prepare is required.
    """
    if symbol.kind=="function" and part=="declaration" and path and Path(path).suffix.lower() in HEADERS:
        p=source_path(engine,path,symbol.name)
        source=Source.load(p)
        declarations=[o for o in source.occurrences if o.name==symbol.name and o.role=="declaration"]
        if len(declarations)!=1:raise SafeError("头文件函数声明不唯一；拒绝跨声明修改。")
        o=declarations[0]
        target=[t for t in source.tokens if o.start<=t.start<o.signature_end]
        wanted,comments,dirs=lex(old_code)
        replacement,new_comments,new_dirs=lex(new_code)
        if not wanted or not replacement or comments or dirs or new_comments or new_dirs:
            raise SafeError("声明参数编辑只接受原函数内的非空代码片段。")
        values=[t.value for t in target];w=[t.value for t in wanted]
        matches=[i for i in range(len(values)-len(w)+1) if values[i:i+len(w)]==w]
        if len(matches)!=1:raise SafeError("旧片段必须唯一位于指定函数声明内。")
        a=target[matches[0]].start;b=target[matches[0]+len(w)-1].end
        text=merge_tokens(source,a,b,new_code)
        updated=Source.load(p,source.encode(text))
        revised=[x for x in updated.occurrences if x.name==symbol.name and x.role=="declaration"]
        if len(revised)!=1:raise SafeError("修改必须保留原函数声明边界。")
        before=signature(source,o);after=signature(updated,revised[0])
        if ([param_core(x) for x in split_params(before.params)] != [param_core(x) for x in split_params(after.params)]
                or [t.value for t in lex(before.prefix+" "+before.suffix)[0]] != [t.value for t in lex(after.prefix+" "+after.suffix)[0]]):
            raise SafeError("头文件短参数编辑只改变默认值；参数身份和类型保持。签名改变请提交.cpp定义。")
        return engine._plan("Write","code",symbol,[(p,source.raw,source.encode(text))],engine._linked(symbol),
                            {p:(old_code,new_code)})
    if symbol.kind!="function" or not symbol.bodyfile or Path(symbol.bodyfile).suffix.lower() in HEADERS:
        return None
    source=Source.load(symbol.bodyfile)
    candidates=[o for o in source.occurrences if o.name==symbol.name and o.role=="definition"]
    if len(candidates)!=1:return None
    o=candidates[0]
    target=[t for t in source.tokens if o.start<=t.start<o.signature_end]
    wanted,comments,dirs=lex(old_code)
    if comments or dirs or not wanted:return None
    values=[t.value for t in target];w=[t.value for t in wanted]
    matched=[i for i in range(len(values)-len(w)+1) if values[i:i+len(w)]==w]
    if len(matched)!=1:return None
    # If the snippet also occurs in the body, default body edit wins.
    bodyvals=[t.value for t in source.tokens if o.open<t.start<o.close]
    if any(bodyvals[i:i+len(w)]==w for i in range(len(bodyvals)-len(w)+1)):return None
    a=target[matched[0]].start;b=target[matched[0]+len(w)-1].end
    prefix=source.text[o.start:a]+new_code+source.text[b:o.signature_end]
    from .cpp import commentless
    content=prefix+"{"+commentless(source.text[o.open+1:o.close])+"}"
    return maintain_function(engine,symbol.bodyfile,content,symbol.name,[],"public")
