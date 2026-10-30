"""Session-local Target pointers and revision-checked, single-range editing."""
from __future__ import annotations

import difflib
import json
import math
import os
import re
import stat
import tempfile
import textwrap
import time
import uuid
from pathlib import Path

from .cpp import Index, Source, Token, SafeError, canonical, inside, sha, lex, pairs, clean_comment, commentless, HEADERS
from .store import Store


FACETS = {"code", "declaration", "definition", "body", "file_header"}


def token_estimate(text: str) -> int:
    # A deliberately labelled heuristic, never advertised as actual model tokens.
    ascii_count = sum(ord(c) < 128 for c in text)
    return math.ceil(ascii_count / 4 + len(text) - ascii_count)


def page(text: str, offset: int = 0, limit: int = 8000) -> dict:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 32000:
        raise SafeError("offset 必须非负；limit 必须为 1..32000 的整数。")
    chunk = text[offset:offset + limit]
    end = offset + len(chunk)
    return {"text": chunk, "chars": len(chunk), "total_chars": len(text), "next_offset": end if end < len(text) else None, "estimated_tokens": token_estimate(chunk), "token_note": "估算：ASCII 字符/4 + 非 ASCII 字符；不是模型精确 token 数"}


class Engine:
    def __init__(self, root: str, store: Store):
        if not Path(root).is_dir():
            raise SafeError("项目目录不存在。")
        self.root = canonical(root)
        self.scope = self.root
        self.store = store
        self.session = uuid.uuid4().hex
        self.index = Index(self.root)
        self.target: str | None = None
        self.container = ""
        self.remembered: dict[str, str] = {}
        self.ticket: dict | None = None
        self.plan: dict | None = None
        self.store.import_legacy(self.root)

    def _refresh(self):
        self.index.refresh()

    def _id(self, name: str) -> str:
        return sha((self.root + "\0" + name).encode())[:16]

    def _find(self, name: str = "", target_id: str = "") -> str:
        self._refresh()
        if target_id:
            found = [n for n in self.index.groups if self._id(n) == target_id]
        else:
            choices = [name, self.container + "::" + name] if self.container else [name]
            found = [n for n in choices if n in self.index.groups]
            if not found:
                found = [n for n in self.index.groups if n.rsplit("::", 1)[-1] == name]
        found = list(dict.fromkeys(n for n in found if any(inside(o.path, self.scope) for o in self.index.groups[n])))
        if len(found) != 1:
            raise SafeError("Target 不唯一或不在当前 scope；请搜索并点选候选。")
        self.index.resolve(found[0])
        return found[0]

    def _current(self):
        if not self.target:
            raise SafeError("当前指针不是函数/变量；请点选 Target。")
        self._refresh()
        return self.index.resolve(self.target)

    def _prefer(self, items, role="definition"):
        matches = [o for o in items if o.role == role]
        return (matches or items)[0]

    def _source(self, occurrence) -> Source:
        source = self.index.sources[occurrence.path]
        # Reads and Prepare must not silently use cached source after external edits.
        if sha(Path(occurrence.path).read_bytes()) != source.revision:
            self.index.stamps.pop(occurrence.path, None)
            raise SafeError("源码在定位期间变化；请重试读取或 Prepare。")
        return source

    def _lock_records(self, items, *, all_file=False):
        found = {}
        for occurrence in items:
            for record in self.store.blocked(occurrence.name, occurrence.path, all_file=all_file):
                found[record["id"]] = record
        return list(found.values())

    def search(self, keyword: str, where: str = "all", limit: int = 20, offset: int = 0):
        if not keyword.strip():
            raise SafeError("请输入名称关键词或注释关键词。")
        if where not in {"all", "name", "comments"} or not 1 <= limit <= 100 or offset < 0:
            raise SafeError("无效搜索参数。")
        self._refresh()
        words = keyword.casefold().split()
        candidates = []
        for name, items in sorted(self.index.groups.items()):
            if not any(inside(o.path, self.scope) for o in items):
                continue
            docs, public_docs = [], []
            for o in items:
                s = self.index.sources[o.path]
                leading = s.leading(o)
                comments = leading + [c for c in s.comments if o.start <= c.start < o.end]
                docs.extend(clean_comment(c.value) for c in comments)
                if Path(o.path).suffix.lower() in HEADERS:
                    public_docs.extend(clean_comment(c.value) for c in leading)
            doc = " ".join(docs)
            name_match = all(w in name.casefold() for w in words)
            comment_match = all(w in doc.casefold() for w in words)
            if not ((where != "comments" and name_match) or (where != "name" and comment_match)):
                continue
            brief = " ".join(public_docs) if name_match and where != "comments" else ""
            if not brief:
                brief = next((d for d in docs if all(w in d.casefold() for w in words)), doc)
            preferred = self._prefer(items, "declaration")
            source = self.index.sources[preferred.path]
            declaration = commentless(source.text[preferred.start:preferred.signature_end]).strip().rstrip(";") + ";"
            candidates.append({"id": self._id(name), "name": name, "kind": preferred.kind, "file": os.path.relpath(preferred.path, self.root), "line": source.text.count("\n", 0, preferred.start) + 1, "signature": declaration[:180], "brief": brief[:120], "ambiguous": self.index.ambiguous(items), "read_only_syntax": any(o.unsafe for o in items)})
        return {"candidates": candidates[offset:offset + limit], "total": len(candidates), "next_offset": offset + limit if offset + limit < len(candidates) else None, "index_complete": not self.index.incomplete, "unparsed_files": len(self.index.errors), "diagnostics": [{"file": os.path.relpath(p, self.root), "error": e} for p, e in list(self.index.errors.items())[:5]]}

    def select(self, name: str = "", target_id: str = ""):
        if not name and not target_id:
            raise SafeError("需要 name 或 target_id。")
        self.abort()
        self.target = None
        self.target = self._find(name, target_id)
        parts = self.target.split("::")
        for i, part in enumerate(parts):
            self.remembered["::".join(parts[:i])] = part
        self.container = "::".join(parts[:-1])
        self.abort()
        return self.status()

    def child(self, name: str = ""):
        if self.target:
            raise SafeError("函数/变量已是叶指针；先 Parent 返回容器。")
        child = name or self.remembered.get(self.container, "")
        if not child:
            raise SafeError("此层没有记忆；请提供子名称或搜索候选。")
        qualified = "::".join(filter(None, [self.container, child]))
        self._refresh()
        if qualified in self.index.groups:
            return self.select(qualified)
        if not any(n.startswith(qualified + "::") for n in self.index.groups):
            raise SafeError("该容器不存在。")
        self.remembered[self.container] = child
        self.container = qualified
        self.abort()
        return self.status()

    def parent(self):
        if self.target:
            self.target = None
        elif self.container:
            self.container = self.container.rpartition("::")[0]
        else:
            self.scope = canonical(Path(self.scope).parent) if self.scope != self.root else self.root
        self.abort()
        return self.status()

    def set_scope(self, path: str):
        self.abort()
        proposed = canonical(Path(self.root) / path)
        if not inside(proposed, self.root) or not Path(proposed).is_dir():
            raise SafeError("scope 必须在启动时选定的项目内；不能通过 MCP 切换项目根。")
        self.scope, self.target, self.container = proposed, None, ""
        self.abort()
        return self.status()

    def status(self):
        trail = [{"kind": "project", "name": Path(self.root).name}, {"kind": "scope", "name": os.path.relpath(self.scope, self.root)}]
        trail.extend({"kind": "container", "name": p} for p in self.container.split("::") if p)
        if self.target:
            trail.append({"kind": "symbol", "name": self.target.rsplit("::", 1)[-1], "id": self._id(self.target)})
        return {"session": self.session[:12], "target": self.target, "trail": trail, "remembered_child": self.remembered.get(self.container), "pending_part": self.ticket["part"] if self.ticket else None, "preview_id": self.plan["id"] if self.plan else None}

    def declaration(self, name: str = "", offset=0, limit=8000):
        # A dependency read is non-mutating. It never switches away from the function being maintained.
        resolved = self._find(name) if name else self.target
        if not resolved:
            raise SafeError("未设置 Target。")
        self._refresh()
        items = self.index.resolve(resolved)
        occurrence = self._prefer(items, "declaration")
        source = self._source(occurrence)
        docs = "\n".join(clean_comment(c.value) for c in source.leading(occurrence))
        # Definitions without a separate header expose signature only, not implementation docs.
        if occurrence.role != "declaration" and Path(occurrence.path).suffix.lower() not in HEADERS:
            docs = ""
        signature = commentless(source.text[occurrence.start:occurrence.signature_end]).strip().rstrip(";") + ";"
        return {"target": resolved, "facet": "interface", **page("\n".join(x for x in [docs, signature] if x), offset, limit)}

    def definition(self, offset=0, limit=8000):
        items = self._current()
        occurrence = self._prefer(items)
        source = self._source(occurrence)
        if occurrence.kind == "function":
            if occurrence.open is None:
                raise SafeError("当前函数只有声明，没有可靠函数体；不会退回头文件。")
            text = source.text[occurrence.open + 1:occurrence.close]
        else:
            text = source.text[occurrence.start:occurrence.end]
        return {"target": self.target, "facet": "code", **page(commentless(text), offset, limit)}

    def _comments(self, items, part):
        if part not in FACETS - {"code"}:
            raise SafeError("注释 part 必须为 declaration/definition/body/file_header。")
        occurrence = self._prefer(items, "declaration" if part in {"declaration", "file_header"} else "definition")
        inline_header = part == "declaration" and occurrence.open is not None and Path(occurrence.path).suffix.lower() in HEADERS
        if part in {"declaration", "definition"} and occurrence.role != part and not inline_header:
            raise SafeError("此 Target 没有该层的声明或定义。")
        source = self._source(occurrence)
        if part == "body":
            comments = [c for c in source.comments if occurrence.open is not None and occurrence.open < c.start < occurrence.close]
        elif part == "file_header":
            comments = source.file_header()
        else:
            comments = source.leading(occurrence)
        return occurrence, source, comments

    def comments(self, part="body", offset=0, limit=8000):
        occurrence, source, comments = self._comments(self._current(), part)
        entries = [{"id": sha((source.revision + str(c.start)).encode())[:12], "line": source.text.count("\n", 0, c.start) + 1, "kind": c.kind, "text": clean_comment(c.value)} for c in comments]
        text = "\n".join(f"[{e['id']}] L{e['line']} {e['text']}" for e in entries)
        result = {"target": self.target, "facet": part, **page(text, offset, limit)}
        return result

    def exact(self, part="definition", offset=0, limit=8000):
        items = self._current()
        occurrence = self._prefer(items, "declaration" if part == "declaration" else "definition")
        source = self._source(occurrence)
        if part == "body" and occurrence.open is not None:
            text = source.text[occurrence.open + 1:occurrence.close]
        elif part in {"declaration", "definition"}:
            comments = source.leading(occurrence)
            start = comments[0].start if comments else occurrence.start
            text = source.text[start:occurrence.end]
        elif part == "file_header":
            text = "\n".join(c.value for c in source.file_header())
        else:
            raise SafeError("无效的原始片段层。")
        return {"target": self.target, "facet": "raw_" + part, "file": os.path.relpath(occurrence.path, self.root), **page(text, offset, limit)}

    def lock_status(self):
        records = self._lock_records(self._current())
        return {"target": self.target, "locked": bool(records), "locks": [{"id": r["id"], "reason": r["reason"], "legacy": bool(r["legacy"])} for r in records]}

    def lock(self, reason=""):
        items = self._current()
        locations = [{"path": o.path, "name": o.name} for o in items]
        self.store.lock(self.root, self.target, locations, reason)
        self.abort()
        return self.lock_status()

    def abort(self):
        self.ticket = self.plan = None
        return {"status": "aborted"}

    def prepare(self, part="code"):
        self.abort()
        if part not in FACETS:
            raise SafeError("无效编辑层。")
        items = self._current()
        if part == "code":
            occurrence = self._prefer(items)
            source = self._source(occurrence)
            if occurrence.kind == "function":
                if occurrence.open is None:
                    raise SafeError("没有可编辑的函数体。")
                start, end = occurrence.open + 1, occurrence.close
            else:
                local = [t for t in source.tokens if occurrence.start <= t.start < occurrence.end]
                equal = next((t for t in local if t.value == "="), None)
                if not equal:
                    raise SafeError("最小实现仅编辑变量已有初始化表达式，不能更改名称/类型。")
                start, end = equal.end, local[-1].start
            result = {"implementation": commentless(source.text[start:end])}
        else:
            occurrence, source, comments = self._comments(items, part)
            start, end = occurrence.start, occurrence.end
            result = {"comments": [{"id": sha((source.revision + str(c.start)).encode())[:12], "text": clean_comment(c.value), "kind": c.kind} for c in comments]}
        if part == "code" and len(result["implementation"]) > 32000:
            result = {"implementation": result["implementation"][:32000], "truncated": True, "next_offset": 32000}
        if part != "code" and len(json.dumps(result, ensure_ascii=False)) > 32000:
            raise SafeError("注释编辑载荷过大；本版本拒绝 Prepare，不输出超量上下文。")
        self.ticket = {"name": self.target, "scope": self.scope, "part": part, "path": occurrence.path, "occurrence": occurrence, "start": start, "end": end, "sources": {o.path: self._source(o).raw for o in items}, "epoch": self.store.epoch(), "revision": uuid.uuid4().hex[:20]}
        self.plan = None
        return {"target": self.target, "part": part, "revision": self.ticket["revision"], "locked": bool(self._lock_records(items, all_file=part == "file_header")), **result}

    def _validate_ticket(self):
        t = self.ticket
        if not t or t["name"] != self.target or t["scope"] != self.scope:
            raise SafeError("没有属于当前 Target 的 Prepare；切换 Target/scope 会清除事务。")
        if t["epoch"] != self.store.epoch():
            raise SafeError("锁状态已变化（包括解锁）；必须重新 Prepare。")
        self._refresh()
        mapped = self.index.resolve(t["name"])
        if {o.path for o in mapped} != set(t["sources"]):
            raise SafeError("Target 的物理映射在 Prepare 后改变；必须重新定位。")
        for path, raw in t["sources"].items():
            if canonical(path) != path or not inside(path, self.root) or Path(path).is_symlink():
                raise SafeError("源码路径边界变化。")
            st = Path(path).stat()
            if st.st_nlink != 1:
                raise SafeError("不允许编辑硬链接源文件。")
            if Path(path).read_bytes() != raw:
                raise SafeError("源码在 Prepare 后变化；必须重新 Prepare。")
        return t

    @staticmethod
    def _format_comment(source: Source, token: Token | None, at: int, new: str) -> str:
        if "*/" in new or "/*" in new or "\x00" in new or any(line.rstrip().endswith("\\") for line in new.splitlines()):
            raise SafeError("注释正文不能含注释边界或行拼接符。")
        newline = "\r\n" if "\r\n" in source.text else "\n"
        line_start = source.text.rfind("\n", 0, at) + 1
        prefix = source.text[line_start:at]
        indent = re.match(r"[ \t]*", prefix).group()
        lines = new.strip().splitlines() or [""]
        if token is None or token.kind == "line":
            marker = re.match(r"//[/!]?(?:<)?", token.value).group() if token else "///"
            text = (newline + indent).join(marker + " " + line for line in lines)
            return text if token else text + newline + indent
        marker = re.match(r"/\*[*!]?", token.value).group()
        if len(lines) == 1 and "\n" not in token.value:
            return marker + " " + lines[0] + " */"
        return marker + newline + newline.join(indent + " * " + line for line in lines) + newline + indent + " */"

    def preview(self, old_code="", new_code="", comment_id=""):
        self.plan = None
        t = self._validate_ticket()
        source = Source.load(t["path"], t["sources"][t["path"]])
        occurrence = t["occurrence"]
        if t["part"] == "code":
            if not old_code.strip():
                raise SafeError("代码替换需要非空的旧片段；不接受整函数删除。")
            if not new_code.strip() and occurrence.kind != "function":
                raise SafeError("空替换仅用于现有函数内部片段；不接受整函数删除。")
            old_tokens, old_comments, old_dirs = lex(old_code)
            new_tokens, new_comments, new_dirs = lex(new_code)
            if old_comments or new_comments:
                raise SafeError("代码编辑不能包含注释；请独立编辑注释。")
            old_tokens = sorted(old_tokens + old_dirs, key=lambda x: x.start)
            new_tokens = sorted(new_tokens + new_dirs, key=lambda x: x.start)
            if not old_tokens or (not new_tokens and new_code.strip()):
                raise SafeError("片段不包含代码 token。")
            pairs(old_tokens)
            pairs(new_tokens)
            body_tokens = sorted((x for x in source.tokens + source.directives if t["start"] <= x.start and x.end <= t["end"]), key=lambda x: x.start)
            old_values = [x.value for x in old_tokens]
            width = len(old_values)
            values = [x.value for x in body_tokens]
            matches = [i for i in range(len(values) - width + 1) if values[i:i + width] == old_values]
            if len(matches) != 1:
                raise SafeError("旧片段在当前目标内未找到或出现多次；需唯一片段。")
            matched = body_tokens[matches[0]:matches[0] + width]
            start, end = matched[0].start, matched[-1].end
            if not new_tokens:
                remaining = [token for token in source.tokens
                             if t["start"] <= token.start and token.end <= t["end"]
                             and (token.end <= start or token.start >= end)]
                if not any(token.value not in {";", "{", "}"} for token in remaining):
                    raise SafeError("Write 不能清空现有函数体；明确删除请使用独立 Delete。")
                replacement = ""
            elif len(new_tokens) == len(matched):
                # Preserve EVERY original token gap, including tabs/CRLF/alignment.
                chunks = []
                for i, token in enumerate(matched):
                    chunks.append(new_tokens[i].value)
                    if i + 1 < len(matched):
                        chunks.append(source.text[token.end:matched[i + 1].start])
                replacement = "".join(chunks)
            else:
                normalized = textwrap.dedent(new_code).strip()
                nl = "\r\n" if "\r\n" in source.text else "\n"
                line_start = source.text.rfind("\n", 0, start) + 1
                indent = re.match(r"[ \t]*", source.text[line_start:start]).group()
                lines = normalized.splitlines()
                replacement = lines[0] + "".join(nl + indent + line for line in lines[1:])
        else:
            _, _, comments = self._comments(self._current(), t["part"])
            chosen = [c for c in comments if sha((source.revision + str(c.start)).encode())[:12] == comment_id] if comment_id else [c for c in comments if old_code in {c.value, clean_comment(c.value)}]
            if comments:
                if len(chosen) != 1:
                    raise SafeError("请选一个 comment_id；注释定位必须唯一。")
                comment = chosen[0]
                start, end = comment.start, comment.end
                if old_code and old_code.strip() not in {comment.value, clean_comment(comment.value)}:
                    block = old_code.strip().replace("\r\n", "\n")
                    if "\r\n" in source.text:
                        block = block.replace("\n", "\r\n")
                    block_tokens, block_comments, block_dirs = lex(block)
                    if (t["part"] != "body" or block_tokens or block_dirs or len(block_comments) < 2
                            or any(c.kind != "line" for c in block_comments)):
                        raise SafeError("注释块 Update 只接受原函数体内连续的行注释。")
                    end = start + len(block)
                    if end > occurrence.close or source.text[start:end] != block:
                        raise SafeError("旧注释块必须从指定 comment_id 开始且不跨函数边界。")
            else:
                if comment_id or old_code or t["part"] == "body":
                    raise SafeError("没有匹配注释；当前版本不支持凭空插入内部行注释。")
                comment = None
                start = end = 0 if t["part"] == "file_header" else occurrence.start
            replacement = self._format_comment(source, comment, start, new_code)
        new_text = source.text[:start] + replacement + source.text[end:]
        new_raw = source.encode(new_text)
        reparsed = Source.load(source.path, new_raw)
        delta = len(replacement) - (end - start)
        # No lexical token may cross the splice boundary (guards token fusion).
        if any(x.start < start < x.end or x.start < start + len(replacement) < x.end for x in reparsed.tokens):
            raise SafeError("替换与邻接 token 粘连；请扩大到完整表达式。")
        if t["part"] != "code":
            if [x.value for x in source.tokens] != [x.value for x in reparsed.tokens]:
                raise SafeError("注释编辑意外改变了代码 token；拒绝写入。")
        else:
            before = [(x.value, x.start, x.end) for x in source.tokens if x.end <= start or x.start >= end]
            after = [(x.value, x.start if x.end <= start else x.start - delta, x.end if x.end <= start else x.end - delta) for x in reparsed.tokens if x.end <= start or x.start >= start + len(replacement)]
            if before != after:
                raise SafeError("编辑影响了授权范围以外的 token。")
        # Symbol topology and signatures must remain unchanged. No brace escape,
        # inserted sibling, renamed Target, or swallowed following function.
        def topology(src):
            return [(o.name, o.kind, o.role, o.args, commentless(src.text[o.start:o.signature_end]) if o.kind == "function" else o.name) for o in src.occurrences]
        if topology(source) != topology(reparsed):
            raise SafeError("替换改变了函数边界、签名或符号结构；拒绝写入。")
        updated = [o for o in reparsed.occurrences if o.name == occurrence.name and o.role == occurrence.role]
        if len(updated) != 1 or (t["part"] == "code" and updated[0].end != occurrence.end + delta):
            raise SafeError("无法复核修改后的 Target 范围。")
        old_fragment = source.text[start:end]
        diff = "\n".join(difflib.unified_diff(old_fragment.splitlines(), replacement.splitlines(), fromfile="目标片段/修改前", tofile="目标片段/修改后", lineterm=""))
        self.plan = {"id": uuid.uuid4().hex[:20], "raw": new_raw, "start": start, "end": end, "old": old_fragment, "new": replacement, "diff": diff}
        return {"preview_id": self.plan["id"], "target": self.target, "part": t["part"], "file": os.path.relpath(source.path, self.root), "before": old_fragment, "after": replacement, "diff": diff, "locked": bool(self.store.blocked(self.target, source.path, all_file=t["part"] == "file_header")), "changed_chars": {"before": len(old_fragment), "after": len(replacement)}, "preserved": "范围外字节、签名、兄弟函数"}

    def replace(self, preview_id=""):
        if not self.plan:
            raise SafeError("必须先成功 Preview；Replace 不接受任意新代码。")
        if preview_id and preview_id != self.plan["id"]:
            raise SafeError("preview_id 不匹配。")
        backup = None
        with self.store.transaction():
            t = self._validate_ticket()
            if self.store.blocked(t["name"], t["path"], all_file=t["part"] == "file_header"):
                raise SafeError("Target 已被用户锁定；MCP 无解锁接口，只能由本机 GUI 人工解除后重新 Prepare。")
            path = Path(t["path"])
            old = t["sources"][t["path"]]
            mode = path.stat().st_mode
            if not mode & stat.S_IWUSR:
                raise SafeError("源文件只读。")
            backup_dir = self.store.path.parent / "backups" / sha(self.root.encode())[:16]
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / (str(time.time_ns()) + "_" + path.name)
            backup.write_bytes(old)
            descriptor, temporary = tempfile.mkstemp(prefix=".winyunq-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(self.plan["raw"])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, stat.S_IMODE(mode))
                if path.read_bytes() != old:
                    raise SafeError("写入前源码再次变化；未覆盖外部修改。")
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        result = {"status": "applied", "target": self.target, "preview_id": self.plan["id"], "backup": str(backup), "preserved": {"outside_range_bytes": True, "signature": True, "siblings": True, "comments": t["part"] == "code"}}
        self.index.stamps.pop(t["path"], None)
        self.abort()
        return result
