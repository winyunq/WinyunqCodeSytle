"""Four public operations: Read, Write (add/modify), Delete, Configure."""
from __future__ import annotations
import difflib
import json
import os
from pathlib import Path
import re
import uuid
from types import SimpleNamespace

from .cpp import SafeError, Source, canonical, clean_comment, commentless, inside, lex, pairs, sha, HEADERS, EXTENSIONS
from .doxygen import Catalog, RangeIndex, Symbol, dump_atomic
from .guard import Engine as SourceGuard, page
from .search import rank
from .transactions import Plan

DOC_PREFIX = "// DoxygenUnrealEngine "
DOC_COMMANDS = {"brief", "details", "param", "tparam", "return", "returns", "retval", "note",
                "warning", "see", "sa", "ref", "code", "endcode", "pre", "post", "since",
                "deprecated", "a", "b", "c", "p", "e", "em", "li", "n"}


class Engine:
    def __init__(self, root, store, doxygen=""):
        if not Path(root).is_dir():
            raise SafeError("项目目录不存在。")
        self.root, self.store = canonical(root), store
        self.session = uuid.uuid4().hex
        self.scope = self.root
        self.catalog = Catalog(self.root, store.path.parent / "DoxygenUE" / sha(self.root.encode())[:20], doxygen)
        self.guard = SourceGuard(self.root, store)
        self.guard.index = RangeIndex(self.catalog)
        self.target, self.container = None, ""
        self.default_locator = None
        self.remembered = {}
        self.plan = None
        self.validator = None
        self.last_quality = None
        from .approvals import init
        init(store)

    def abort(self):
        from .approvals import cancel
        cancel(self.store,self.root,self.session)
        self.guard.abort()
        self.plan = None
        return {"status": "aborted"}

    def _locator(self, symbol):
        """Public locators are ordinary names/paths, never an approval token."""
        return {"name": symbol.name, "path": os.path.relpath(symbol.file, self.root)}

    def _activate(self, symbol):
        # An operation may address another symbol without replacing the defaults.
        # A prepared edit must not follow that temporary binding to another file.
        if self.guard.index.bound_id != symbol.id:
            self.guard.abort()
        self.guard.index.bound_id = symbol.id
        self.guard.target, self.guard.scope = symbol.name, self.scope

    def _select(self, symbol):
        if self.target != symbol.id:
            self.abort()
        self.target = symbol.id  # Internal catalog identity, not an MCP parameter.
        self.default_locator = self._locator(symbol)
        self._activate(symbol)
        self.container = symbol.name.rpartition("::")[0]
        parts = symbol.name.split("::")
        for i, part in enumerate(parts):
            self.remembered["::".join(parts[:i])] = symbol.id if i == len(parts)-1 else "::".join(parts[:i+1])

    def _path_filter(self, symbols, path=""):
        if not path:
            return [s for s in symbols if any(inside(p, self.scope) for p in (s.file, s.bodyfile) if p)]
        p = canonical(Path(self.root) / path)
        if not inside(p, self.scope) or not Path(p).is_file():
            raise SafeError("path 必须指向当前 scope 内存在的源码文件。")
        return [s for s in symbols if p in (s.file, s.bodyfile)]

    def _resolve_symbol(self, name="", path=""):
        """Explicit fields override defaults. Mutation lookup is never fuzzy.

        Omitting name uses the remembered leaf. A new explicit name does not
        inherit the old leaf's file; its containing namespace/class is a hint.
        All resulting locations still pass Doxygen/range/lock/revision checks.
        """
        self.catalog.ensure()
        if not name:
            if not self.target:
                raise SafeError("缺少对象名称：请在本次调用提供 name，或使用已记忆的 Target 缺省值。")
            try:
                current = self.catalog.by_id(self.target)
            except SafeError:
                # A changed signature may change Doxygen's internal cache key.
                # Rebind the remembered ordinary locator, never a fuzzy candidate.
                locator = self.default_locator or {}
                choices = self._path_filter([s for s in self.catalog.symbols if s.name == locator.get("name")], locator.get("path", ""))
                if len(choices) != 1:
                    raise SafeError("默认对象已失效；请提供名称。不会改用其他近似对象。")
                current = choices[0]
                self.target = current.id
            if not path:
                if not self._path_filter([current]):
                    raise SafeError("默认对象不在当前 scope。")
                return current
            name = current.name
        name = name.strip()
        if not name:
            raise SafeError("显式 name 不能为空白。")
        symbols = self._path_filter(self.catalog.symbols, path)
        if "::" not in name and self.container:
            qualified = self.container + "::" + name
            matches = [s for s in symbols if s.name == qualified]
        else:
            matches = []
        if not matches:
            matches = [s for s in symbols if s.name == name]
        if not matches and "::" not in name:
            matches = [s for s in symbols if s.name.rsplit("::", 1)[-1] == name]
        if not matches and path:
            source_path = canonical(Path(self.root) / path)
            if (inside(source_path, self.scope) and Path(source_path).is_file()
                    and Path(source_path).suffix.lower() in EXTENSIONS):
                source = Source.load(source_path)
                definitions = [o for o in source.occurrences if o.kind == "function"
                    and o.role == "definition" and (o.name == name or
                    ("::" not in name and o.name.rsplit("::", 1)[-1] == name))]
                if len(definitions) == 1:
                    o = definitions[0]
                    first = source.text.count("\n", 0, o.start) + 1
                    last = source.text.count("\n", 0, o.end - 1) + 1
                    symbol = Symbol("source_" + sha((source_path + "\0" + o.name).encode())[:32],
                        "", o.name, "function", commentless(source.text[o.start:o.signature_end]).strip(),
                        "", source_path, first, source_path, first, last, "public", "", "", "")
                    self.catalog.symbols.append(symbol)
                    self.catalog.hashes[source_path] = sha(source.raw)
                    matches = [symbol]
        if len(matches) != 1:
            raise SafeError("名称未找到或不唯一；请补充完整 name 或 path。不能唯一定位的重载拒绝操作，不要求提交 ID。")
        return matches[0]

    def _symbol(self, name="", path=""):
        symbol = self._resolve_symbol(name, path)
        self._activate(symbol)
        return symbol

    def _linked(self, s):
        return {p: Path(p).read_bytes() for p in set(filter(None, [s.file, s.bodyfile]))}

    def _locks(self, s, all_file=False):
        return [(s.name, p, all_file) for p in set(filter(None, [s.file, s.bodyfile]))]

    def _locked(self, s, all_file=False):
        return any(self.store.blocked(s.name, p, all_file=all_file) for p in (s.file, s.bodyfile) if p)

    def _doc_path(self, s):
        return self.catalog.docs_dir / (s.id + ".dox")

    def _doc(self, s):
        path = self._doc_path(s)
        if path.is_symlink() or not inside(path, self.root):
            raise SafeError("文档路径越界。")
        if not path.exists():
            return None, ""
        raw = path.read_text(encoding="utf-8-sig")
        first, _, body = raw.partition("\n")
        if not first.startswith(DOC_PREFIX):
            raise SafeError("该文档不是受管侧车文档；不会覆盖。")
        meta = json.loads(first[len(DOC_PREFIX):])
        if meta.get("target_id") != s.id:
            raise SafeError("侧车文档 Target 身份不匹配。")
        text = clean_comment(body.strip())
        lines = text.splitlines()
        return meta, "\n".join(lines[1:]).strip()

    def _code_revision(self, s):
        try:
            occurrences = self.guard.index.resolve(s.name)
            values = []
            for o in occurrences:
                source = self.guard.index.sources[o.path]
                ts, _, _ = lex(source.text[o.start:o.end])
                values.append((o.role, [t.value for t in ts]))
            return sha(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()), "symbol_tokens"
        except (SafeError, UnicodeError):
            return sha(json.dumps({p: sha(b) for p, b in self._linked(s).items()}, sort_keys=True).encode()), "source_files_conservative"

    def _documentation_status(self, s):
        meta, _ = self._doc(s)
        revision, basis = self._code_revision(s)
        return {"external_document_exists": meta is not None,
                "needs_review": meta is None or meta.get("reviewed_code_hash") != revision,
                "revision_basis": basis, "code_revision": revision}

    def _header_docs(self, s):
        if Path(s.file).suffix.lower() not in HEADERS:
            return ""
        try:
            source = Source.load(s.file)
            choices = [o for o in source.occurrences if o.name == s.name and
                       source.text.count("\n", 0, o.start)+1 <= s.line <= source.text.count("\n", 0, o.end-1)+1]
            if len(choices) == 1:
                return "\n".join(clean_comment(c.value) for c in source.leading(choices[0]))
        except (OSError, ValueError, UnicodeError):
            pass
        return ""

    def read(self, query="", view="auto", limit=None, offset=0, select=None, kind="", part="body", start=0, max_chars=4000, name="", path="", base="HEAD", target="WORKTREE", detail=False):
        if limit is None:
            limit = 50 if view in {"inventory","impact","history","changes"} else 1
        if view in {"capabilities", "inventory", "impact", "history", "changes"}:
            from . import inspection
            if view == "capabilities": return inspection.CAPABILITIES.copy()
            if view == "inventory": return inspection.inventory(self,limit,offset)
            if view == "impact": return inspection.impact(self,name,path,limit,offset)
            if view == "history": return inspection.history(self,limit)
            from .changes import compare
            return compare(self,base,target,name,path,detail,limit,offset)
        if not 1 <= limit <= 50 or offset < 0 or len(query) > 300:
            raise SafeError("limit 为 1..50，offset 非负，query 最长 300 字符。")
        if query.strip() and name:
            raise SafeError("query 是搜索词，name 是精确定位；一次调用只能指定一个。")
        if view == "auto":
            view = "brief" if query.strip() else "overview"
        self.catalog.ensure()
        search_info = None
        if query.strip():
            hits = rank(self._path_filter(self.catalog.symbols, path), query, self.catalog.settings["aliases"], self.scope, kind)
            chosen = hits[offset:offset+limit]
            candidates = [{**{k: v for k, v in s.summary(self.root).items() if k != "id"},
                           "score": score, "match": reason, "is_suggestion": not exact}
                          for s, score, reason, exact in chosen]
            if limit != 1 or not chosen:
                return {"query": query, "results": candidates, "total": len(hits),
                        "target_unchanged": True, "ranking": "词法/注释/显式同义词/拼写相似度；分数不是概率"}
            symbol, score, reason, exact = chosen[0]
            unique_exact = exact and sum(h[3] for h in hits) == 1
            if select is not False:
                self._select(symbol)
            search_info = {"query": query, "match": reason, "score": score, "total": len(hits),
                           "is_suggestion": not unique_exact}
        else:
            symbol = self._resolve_symbol(name, path)
            if select is True:
                self._select(symbol)
        if any(sha(Path(p).read_bytes()) != self.catalog.hashes.get(p) for p in (symbol.file, symbol.bodyfile) if p):
            self.catalog.ensure(force=True)
            symbol = self.catalog.by_id(symbol.id)
        previous_guard = self.guard.target, self.guard.index.bound_id
        self.guard.target, self.guard.index.bound_id = symbol.name, symbol.id
        try:
            if view in {"brief", "overview", "details", "documentation"}:
                from .views import projection
                result = {"projection": projection(symbol, "details" if view == "documentation" else view)}
                # Diagnostic/raw display remains local to Engine; RPC maps projection only.
                result["text"] = json.dumps(result["projection"], ensure_ascii=False, separators=(",", ":"))
                if self._doc_path(symbol).exists():
                    result["documentation"] = self._documentation_status(symbol)
                    if result["documentation"]["needs_review"]:
                        result["projection"]["documentation_needs_review"] = True
            elif view == "interface":
                _, docs = self._doc(symbol)
                content = "\n".join(x for x in (symbol.signature, self._header_docs(symbol), docs) if x)
                result = {**page(content, start, max_chars), "documentation": self._documentation_status(symbol)}
                from .views import projection
                result["projection"] = projection(symbol, "overview")
            elif view == "code":
                result = self.guard.definition(start, max_chars)
            elif view == "comments":
                result = self.guard.comments(part, start, max_chars)
                _, source, comments = self.guard._comments(self.guard._current(), part)
                result["projection"] = {"comments": [{"comment_id": sha((source.revision + str(c.start)).encode())[:12], "text": clean_comment(c.value)} for c in comments]}
            elif view == "raw":
                result = self.guard.exact("definition" if part == "body" else part, start, max_chars)
            elif view == "external_document":
                _, content = self._doc(symbol)
                result = {**page(content, start, max_chars), "documentation": self._documentation_status(symbol),
                          "document_file": os.path.relpath(self._doc_path(symbol), self.root)}
            else:
                raise SafeError("未知读取视图。")
        finally:
            self.guard.target, self.guard.index.bound_id = previous_guard
        result.update({"target": self._locator(symbol), "name": symbol.name, "view": view, "locked": self._locked(symbol)})
        if search_info:
            result["search"] = search_info
        return result

    def _plan(self, action, kind, s, changes, guards, fragments=None, reason="", all_file=False):
        self.plan = Plan(action, kind, self.target, self.store.epoch(), changes, guards,
                         self._locks(s, all_file) if s else [], reason,
                         locator=self._locator(s) if s else None)
        result = self.plan.preview(self.root, fragments)
        result["locked"] = self._locked(s, all_file) if s else False
        return result

    def _apply(self, action, preview_id):
        if not preview_id or not self.plan or self.plan.id != preview_id or self.plan.action != action:
            raise SafeError("必须提交同一操作的预览 ID；Write 不能提交 Delete 事务，反之亦然。")
        return self.plan.apply(self)

    @staticmethod
    def _no_deletion(old_code, new_code, allow_empty_fragment=False):
        before, bc, bd = lex(old_code)
        after, ac, ad = lex(new_code)
        after = after + ad
        if bc or ac:
            raise SafeError("代码增改不能携带注释。")
        if not after or not new_code.strip():
            if allow_empty_fragment and before:
                return
            raise SafeError("Write 不能清空片段；请使用独立 Delete。")
        if not any(t.value not in {";", "{", "}"} for t in after):
            raise SafeError("Write 不能把代码清空为分号/空块；明确删除请使用 Delete。")
        # Editing is replacement, not monotone token growth. Shorter expressions
        # are legal. The source guard protects the selected range and siblings.

    def write(self, action="preview", kind="code", operation="modify", old_code="", new_code="", part=None,
              comment_id="", preview_id="", placement="after", path="", name="", comment_style="preserve", includes=None, access="public", fields=None, members=None):
        if part is None:
            part = "declaration" if fields is not None else "body"
        if action == "apply":
            if old_code or new_code or path or comment_id or name or includes or fields or members:
                raise SafeError("Apply 只接受已有 preview_id，不接受新载荷。")
            return self._apply("Write", preview_id)
        self.plan = None
        if action == "prepare":
            self.abort()
        if action not in {"prepare", "preview"}:
            raise SafeError("Write action 只能为 prepare/preview/apply。")
        if len(new_code) > 1048576 or len(old_code) > 1048576:
            raise SafeError("编辑片段超过 1048576 字符。")
        if kind == "code" and operation in {"function", "include"}:
            if action != "preview":
                raise SafeError("function/include 使用 preview→apply；不要求另行 Prepare。")
            from .maintenance import maintain_function, maintain_includes
            if operation == "include":
                if old_code:
                    from .maintenance import edit_include
                    return edit_include(self,path,name,old_code,new_code)
                return maintain_includes(self, path, name, includes or ([new_code] if new_code else []))
            return maintain_function(self, path, new_code, name, includes or [], access)
        if operation == "add_member":
            if kind != "code" or action != "preview":
                raise SafeError("add_member 仅支持 code preview。")
            return self._add_member(name, path, new_code, includes or [])
        if operation == "modify_member":
            if kind != "code" or action != "preview":
                raise SafeError("modify_member 仅支持 code preview。")
            return self._modify_member(name, path, old_code, new_code)
        if operation == "modify_members":
            if kind != "code" or action != "preview":
                raise SafeError("modify_members 仅支持 code preview。")
            return self._modify_members(name, path, members or [])
        if operation == "modify_local_initializers":
            if kind != "code" or action != "preview":
                raise SafeError("modify_local_initializers 仅支持 code preview。")
            return self._modify_local_initializers(path, members or [])
        if operation == "modify_smoke_tank_target":
            if kind != "code" or action != "preview":
                raise SafeError("modify_smoke_tank_target 仅支持 code preview。")
            return self._modify_smoke_tank_target(path, old_code, new_code)
        if operation == "add_symbol":
            if kind != "code" or action != "preview":
                raise SafeError("add_symbol 仅支持 code preview。")
            if name:
                raise SafeError("add_symbol 的新符号名称在 new_code 中给出；path 可省略并使用默认对象所在文件。")
            if not path and self.target:
                default = self._resolve_symbol()
                path = os.path.relpath(default.bodyfile or default.file, self.root)
            ts, cs, ds = lex(new_code)
            if any(t.value == "::" for t in ts):
                from .maintenance import maintain_function
                return maintain_function(self, path, new_code, "", includes or [], access, add_only=True)
            return self._add_symbol(path, new_code, includes or [])
        if operation not in {"modify", "add"}:
            raise SafeError("Write 只能增加和修改。删除必须调用 Delete。")
        if fields is not None:
            if kind != "comment" or part != "declaration" or action != "preview" or old_code or new_code:
                raise SafeError("fields 用于声明前注释的 preview；不混用原始注释载荷。")
            from .source_docs import update_fields
            return update_fields(self,name,path,fields)
        if kind == "comment" and comment_style == "doxygen":
            if part != "declaration" or comment_id:
                raise SafeError("Doxygen 分组注释编辑仅支持 declaration；内部单条注释使用 preserve。")
            from .source_docs import source_comment
            return source_comment(self, name, path, action, old_code, new_code, operation)
        s = self._symbol(name, path)
        if kind == "documentation":
            meta, text = self._doc(s)
            if action == "prepare":
                return {"target": self._locator(s), "text": text, **self._documentation_status(s), "locked": self._locked(s)}
            if not new_code.strip():
                raise SafeError("Write 不能删除/清空文档；请调用 Delete(kind='documentation')。")
            if operation == "add" and meta is not None:
                raise SafeError("文档已经存在；使用 modify。")
            if "*/" in new_code or "/*" in new_code or re.search(r"<\s*/?\s*[A-Za-z]", new_code):
                raise SafeError("文档正文不能注入注释边界。")
            commands = set(re.findall(r"[@\\]([A-Za-z]+)", new_code))
            if commands - DOC_COMMANDS:
                raise SafeError("文档含未允许的 Doxygen 命令；结构绑定及外部文件包含由程序控制。")
            code_revision, basis = self._code_revision(s)
            meta = {"schema": 1, "target_id": s.id, "name": s.name,
                    "declaration_file": os.path.relpath(s.file, self.root), "signature": s.signature,
                    "reviewed_code_hash": code_revision, "revision_basis": basis}
            command = "fn" if s.kind == "function" else "var"
            if s.kind not in {"function", "variable"}:
                raise SafeError("外置对象文档目前支持函数和变量。")
            binding = " ".join(s.signature.rstrip(";").split())
            if "*/" in binding or "/*" in binding or "\x00" in binding:
                raise SafeError("签名含不能安全置入Doxygen注释的字面量；拒绝生成外置绑定。")
            document = DOC_PREFIX + json.dumps(meta, ensure_ascii=False) + "\n/**\n * @" + command + " " + binding + "\n"
            document += "\n".join(" * " + line for line in new_code.strip().splitlines()) + "\n */\n"
            p = self._doc_path(s)
            return self._plan("Write", kind, s, [(canonical(p), p.read_bytes() if p.exists() else None, document.encode())],
                              self._linked(s), {canonical(p): (text, new_code)})
        if kind not in {"code", "comment"}:
            raise SafeError("Write kind 只能是 code/documentation/comment。")
        if kind == "code" and action == "preview" and operation == "modify":
            from .maintenance import try_signature_edit
            synced = try_signature_edit(self,s,old_code,new_code,path,part)
            if synced is not None:
                return synced
        facet = "code" if kind == "code" else part
        if kind == "comment" and not new_code.strip() and action == "preview":
            raise SafeError("Write 不能清空注释；请调用 Delete(kind='comment')。")
        if action == "prepare":
            self.plan = None
            prepared = self.guard.prepare(facet)
            prepared["target"] = self._locator(s)
            return prepared
        if not self.guard.ticket or self.guard.ticket["part"] != facet or self.guard.ticket["name"] != s.name:
            self.guard.prepare(facet)
        if kind == "code":
            if operation == "add":
                if placement not in {"before", "after"} or not old_code.strip():
                    raise SafeError("增加代码需要唯一旧片段作为锚点，placement 为 before/after。")
                new_code = new_code + "\n" + old_code if placement == "before" else old_code + "\n" + new_code
            self._no_deletion(old_code, new_code, allow_empty_fragment=operation == "modify" and part == "body")
        result = self.guard.preview(old_code, new_code, comment_id)
        t, gp = self.guard.ticket, self.guard.plan
        p = t["path"]
        return self._plan("Write", kind, s, [(p, t["sources"][p], gp["raw"])], t["sources"],
                          {p: (gp["old"], gp["new"])}, all_file=facet == "file_header")

    def _add_symbol(self, path, content, includes=None):
        self.catalog.ensure()
        p = Path(path)
        if not path or p.is_absolute() or ".." in p.parts:
            raise SafeError("新增符号需要项目内相对文件路径。")
        p = Path(self.root) / p
        if not inside(p, self.scope) or p.suffix.lower() not in EXTENSIONS or p.is_symlink():
            raise SafeError("新增路径不在 scope 或不是 C/C++ 源码。")
        if not content.strip() or len(content) > 32000:
            raise SafeError("新增符号不能为空或过大。")
        ts, cs, ds = lex(content)
        if cs or ds:
            raise SafeError("新增代码不得携带注释/预处理指令；文档单独写。")
        fragment = Source.load(str(p), content.encode())
        struct_container = None
        if (len(fragment.containers) == 1
                and fragment.containers[0].kind == "struct"
                and not fragment.containers[0].templated
                and re.match(r"\s*USTRUCT\s*\(", content)
                and len(re.findall(r"\bUPROPERTY\s*\(", content)) == len(fragment.occurrences)
                and fragment.occurrences
                and all(o.kind == "variable" and o.role == "declaration" and not o.unsafe
                        and fragment.containers[0].start < o.start < o.end < fragment.containers[0].close
                        for o in fragment.occurrences)
                and not fragment.comments and not fragment.directives):
            struct_container = fragment.containers[0]
            symbol_name = struct_container.name
            member_names = {o.name.rsplit("::", 1)[-1] for o in fragment.occurrences}
            if len(member_names) != len(fragment.occurrences):
                raise SafeError("USTRUCT 新成员名重复。")
            if any(s.name == symbol_name or s.name.startswith(symbol_name + "::") for s in self.catalog.symbols):
                raise SafeError("USTRUCT 或其成员已经存在；不能覆盖或制造不明确名称。")
        else:
            if len(fragment.occurrences) != 1 or fragment.occurrences[0].unsafe:
                raise SafeError("一次只增加一个能安全复核的独立函数/变量或 USTRUCT。")
            added = fragment.occurrences[0]
            symbol_name = added.name
            member_names = set()
            existing = [s for s in self.catalog.symbols if s.name == symbol_name]
            if existing:
                if (len(existing) != 1 or added.kind != "function" or added.role != "definition"
                        or existing[0].kind != "function" or existing[0].bodyfile):
                    raise SafeError("符号已经存在；不能通过增加覆盖或制造不明确重载。")
                declaration_source = Source.load(existing[0].file)
                declarations = [o for o in declaration_source.occurrences
                                if o.name == symbol_name and o.role == "declaration"]
                if len(declarations) != 1 or declarations[0].args != added.args:
                    raise SafeError("已有声明与新定义不能唯一配对或参数不一致。")
        old = p.read_bytes() if p.exists() else None
        if old is not None and canonical(p) not in self.catalog.hashes:
            raise SafeError("文件未在 Doxygen 输入索引中；拒绝向隐藏/排除的文件追加。")
        source = Source.load(str(p), old or b"")
        condition_depth = 0
        for directive in source.directives:
            if re.match(r"#\s*(if|ifdef|ifndef)\b", directive.value):
                condition_depth += 1
            elif re.match(r"#\s*endif\b", directive.value):
                condition_depth -= 1
                if condition_depth < 0:
                    raise SafeError("条件编译边界不完整；拒绝追加符号。")
            elif re.match(r"#\s*(else|elif)\b", directive.value) and condition_depth == 0:
                raise SafeError("条件编译边界不完整；拒绝追加符号。")
        if condition_depth != 0:
            raise SafeError("条件编译边界不完整；拒绝追加符号。")
        nl = "\r\n" if "\r\n" in source.text else "\n"
        suffix = nl + content.replace("\r\n", "\n").replace("\n", nl).strip() + nl
        new = source.encode(source.text + suffix)
        check = Source.load(str(p), new)
        before = [(o.name, o.kind, o.role, o.args) for o in source.occurrences]
        after = [(o.name, o.kind, o.role, o.args) for o in check.occurrences]
        if struct_container:
            new_member_symbols = {
                f"{symbol_name}::{member_name}" for member_name in member_names
            }
            expected_members = [
                (o.name, o.kind, o.role, o.args)
                for o in fragment.occurrences
            ]
            if (after[:-len(expected_members)] != before
                    or after[-len(expected_members):] != expected_members):
                raise SafeError("新增 USTRUCT 改变了原有符号结构。")
            before_containers = [(c.name, c.kind, c.templated) for c in source.containers]
            after_containers = [(c.name, c.kind, c.templated) for c in check.containers]
            if after_containers != before_containers + [(symbol_name, "struct", False)]:
                raise SafeError("新增 USTRUCT 改变了原有类型结构。")
        elif after != before + [(symbol_name, fragment.occurrences[0].kind,
                                 fragment.occurrences[0].role, fragment.occurrences[0].args)]:
            raise SafeError("新增改变了原有符号结构。")
        from .maintenance import with_includes
        new, include_changed = with_includes(canonical(p), new, includes or [])
        result = self._plan("Write", "add_symbol", None, [(canonical(p), old, new)], {})
        lock_names = [symbol_name]
        if struct_container:
            lock_names.extend(f"{symbol_name}::{member_name}" for member_name in member_names)
        self.plan.locks = [(item, canonical(p), include_changed) for item in lock_names]
        result["locked"] = any(self.store.blocked(item,canonical(p),all_file=include_changed) for item in lock_names)
        hits = rank(self.catalog.symbols, symbol_name.rsplit("::",1)[-1], self.catalog.settings["aliases"], self.scope, "")[:3]
        result["reuse_candidates"] = [{"name": s.name, "brief": s.brief} for s,_,_,_ in hits]
        result["added_symbol"] = symbol_name
        if struct_container:
            result["added_members"] = sorted(member_names)
        return result

    def _modify_local_initializers(self, path, members):
        relative = Path(path)
        if (not path or relative.is_absolute() or ".." in relative.parts
                or relative.suffix.lower() not in {".cpp", ".cc", ".cxx"}
                or not members or len(members) > 32):
            raise SafeError("匿名命名空间常量修改需要项目内 .cpp 路径和有界字段清单。")
        target = Path(self.root) / relative
        p = canonical(target)
        if not inside(p, self.scope) or target.is_symlink() or not target.is_file():
            raise SafeError("匿名命名空间常量不在当前源码范围内。")
        source = Source.load(p)
        replacements = []
        names = set()
        expression = re.compile(r'TEXT\("/Game/Unit/Actor/Army/Tank/[A-Za-z0-9_./]+"\)\Z')
        for member in members:
            name = member.get("name", "")
            old_code = member.get("old_code", "")
            new_code = member.get("new_code", "")
            fullname = name if name.startswith("<anonymous>::") else "<anonymous>::" + name
            if (not name or fullname in names or not expression.fullmatch(old_code)
                    or not expression.fullmatch(new_code)):
                raise SafeError("每个匿名常量必须唯一指定并只替换完整坦克资源路径表达式。")
            matches = [o for o in source.occurrences
                       if o.name == fullname and o.kind == "variable" and o.role == "definition"]
            if len(matches) != 1:
                raise SafeError("匿名常量未找到或不唯一。")
            occurrence = matches[0]
            local = source.text[occurrence.start:occurrence.end]
            if local.count(old_code) != 1:
                raise SafeError("匿名常量旧值未找到或不唯一。")
            start = occurrence.start + local.index(old_code)
            replacements.append((start, start + len(old_code), new_code))
            names.add(fullname)
        updated = source.text
        for start, end, new_code in sorted(replacements, reverse=True):
            updated = updated[:start] + new_code + updated[end:]
        after = Source.load(p, source.encode(updated))
        before_symbols = [(o.name, o.kind, o.role, o.args, o.unsafe) for o in source.occurrences]
        after_symbols = [(o.name, o.kind, o.role, o.args, o.unsafe) for o in after.occurrences]
        if (before_symbols != after_symbols
                or [c.value for c in source.comments] != [c.value for c in after.comments]
                or [d.value for d in source.directives] != [d.value for d in after.directives]):
            raise SafeError("匿名常量修改改变了其他符号、注释或预处理指令。")
        if updated == source.text:
            return {"status": "unchanged", "files": []}
        result = self._plan("Write", "modify_local_initializers", None,
                            [(p, source.raw, source.encode(updated))], {})
        self.plan.locks = [(name, p, False) for name in names]
        result["locked"] = any(self.store.blocked(name, p) for name in names)
        return result

    def _modify_smoke_tank_target(self, path, old_code, new_code):
        expected = "Source/Winyunq/Private/Tests/WinyunqRTSCommandRuntimeSmoke.cpp"
        if path.replace("\\", "/") != expected:
            raise SafeError("只能修改既有 RTS 战斗烟测中的默认目标坦克。")
        old = 'TEXT("/Game/Unit/Actor/Army/Tank/Common/Gen_Common_MediumTank_LowPoly/Common_MediumTank_LowPoly.Common_MediumTank_LowPoly")'
        if (old_code != old or not re.fullmatch(
                r'TEXT\("/Game/Unit/Actor/Army/Tank/Common/Gen_Common_[A-Za-z0-9_]+/Common_[A-Za-z0-9_]+\.Common_[A-Za-z0-9_]+"\)',new_code)):
            raise SafeError("默认目标只能由旧低模坦克改为通用坦克资源路径。")
        target = Path(self.root) / expected
        p = canonical(target)
        if not inside(p, self.scope) or target.is_symlink() or not target.is_file():
            raise SafeError("烟测源码不在当前维护范围。")
        source = Source.load(p)
        marker = "FString TargetPath = " + old_code + ";"
        if source.text.count(marker) != 1:
            raise SafeError("烟测默认目标旧值未找到或不唯一。")
        updated = source.text.replace(marker,"FString TargetPath = " + new_code + ";")
        after = Source.load(p,source.encode(updated))
        before_symbols = [(o.name,o.kind,o.role,o.args,o.unsafe) for o in source.occurrences]
        after_symbols = [(o.name,o.kind,o.role,o.args,o.unsafe) for o in after.occurrences]
        if (before_symbols != after_symbols
                or [c.value for c in source.comments] != [c.value for c in after.comments]
                or [d.value for d in source.directives] != [d.value for d in after.directives]):
            raise SafeError("烟测目标修改改变了其他符号、注释或预处理指令。")
        result = self._plan("Write","modify_smoke_tank_target",None,
                            [(p,source.raw,source.encode(updated))],{})
        self.plan.locks = [("FRTSMoveSmokeState::Tick",p,False)]
        result["locked"] = self.store.blocked("FRTSMoveSmokeState::Tick",p)
        return result

    def _add_member(self, name, path, content, includes=None):
        try:
            symbol = self._symbol(name, path)
        except SafeError as error:
            if not name or "::" not in name or not path or not str(error).startswith("名称未找到或不唯一"):
                raise
            source_path = canonical(Path(self.root) / path)
            if (not inside(source_path, self.scope) or not Path(source_path).is_file()
                    or Path(source_path).suffix.lower() not in HEADERS):
                raise
            if any(s.name == name and source_path in (s.file, s.bodyfile) for s in self.catalog.symbols):
                raise
            source = Source.load(source_path)
            members = [o for o in source.occurrences if o.name == name
                       and o.kind == "variable" and o.role == "declaration"]
            if len(members) != 1 or members[0].unsafe:
                raise
            anchor = members[0]
            first = source.text.count("\n", 0, anchor.start) + 1
            last = source.text.count("\n", 0, anchor.end - 1) + 1
            symbol = Symbol("source_" + sha((source_path + "\0" + name).encode())[:32],
                            "", name, "variable", commentless(source.text[anchor.start:anchor.end]).strip(),
                            "", source_path, first, source_path, first, last, "public", "", "", "")
            self.catalog.symbols.append(symbol)
            self.catalog.hashes[source_path] = sha(source.raw)
            self._activate(symbol)
        if symbol.kind != "variable" or Path(symbol.file).suffix.lower() not in HEADERS:
            raise SafeError("add_member 需要精确定位头文件中的成员变量。")
        if self._locked(symbol, all_file=True):
            raise SafeError("成员或所在源码已锁定。")
        source = Source.load(symbol.file)
        anchors = [o for o in source.occurrences if o.name == symbol.name
                   and o.kind == "variable" and o.role == "declaration"]
        if len(anchors) != 1 or anchors[0].unsafe:
            raise SafeError("成员锚点不唯一或位于不支持的语法中。")
        anchor = anchors[0]
        parents = [c for c in source.containers if c.kind in {"class", "struct"}
                   and c.open < anchor.start < anchor.end < c.close]
        if not parents:
            raise SafeError("成员锚点不属于可编辑的 class/struct。")
        owner = max(parents, key=lambda c: c.open)
        if self.store.blocked(owner.name, canonical(symbol.file), all_file=True):
            raise SafeError("所在类型或源码已锁定。")
        fragment = Source.load(symbol.file, content.encode("utf-8"))
        if (fragment.comments or fragment.directives or fragment.containers or not fragment.occurrences
                or any(o.kind != "variable" or o.role != "declaration" or o.unsafe
                       for o in fragment.occurrences)):
            raise SafeError("add_member 仅接受不含注释、指令、函数或嵌套类型的成员声明。")
        member_names = [o.name.rsplit("::", 1)[-1] for o in fragment.occurrences]
        if len(set(member_names)) != len(member_names):
            raise SafeError("新增成员名重复。")
        existing_names = {o.name.rsplit("::", 1)[-1] for o in source.occurrences
                          if o.kind == "variable" and owner.start < o.start < o.end < owner.close}
        if existing_names.intersection(member_names):
            raise SafeError("新增成员名已在该类型中使用。")
        p = Path(symbol.file)
        if p.is_symlink() or not inside(p, self.scope):
            raise SafeError("新增成员路径不在当前 scope。")
        nl = "\r\n" if "\r\n" in source.text else "\n"
        line_start = source.text.rfind("\n", 0, anchor.start) + 1
        anchor_line = source.text[line_start:anchor.start]
        indent = anchor_line[:len(anchor_line) - len(anchor_line.lstrip(" \t"))]
        lines = content.strip().replace("\r\n", "\n").replace("\r", "\n").split("\n")
        addition = nl.join(indent + line.lstrip(" \t") if line.strip() else "" for line in lines)
        new_text = source.text[:anchor.end] + nl + addition + source.text[anchor.end:]
        new_bytes = source.encode(new_text)
        from .maintenance import with_includes
        new_bytes, include_changed = with_includes(canonical(p), new_bytes, includes or [])
        check = Source.load(str(p), new_bytes)
        full_names = {f"{owner.name}::{member_name}" for member_name in member_names}
        before = self._token_topology(source)
        after = self._token_topology(check)
        if [item for item in after if item[0] not in full_names] != before:
            raise SafeError("新增成员改变了目标范围以外的符号结构。")
        added = [o for o in check.occurrences if o.name in full_names]
        if len(added) != len(full_names) or any(o.kind != "variable" or o.role != "declaration" for o in added):
            raise SafeError("新增成员未能唯一解析为 class/struct 字段。")
        guards = {canonical(p): source.raw}
        result = self._plan("Write", "code", symbol,
                            [(canonical(p), source.raw, new_bytes)], guards,
                            {canonical(p): (source.text, new_bytes.decode("utf-8-sig"))})
        lock_names = [symbol.name, owner.name, *full_names]
        self.plan.locks = [(item, canonical(p), include_changed) for item in lock_names]
        result["locked"] = any(self.store.blocked(item, canonical(p), all_file=include_changed)
                               for item in lock_names)
        result["owner"] = owner.name
        result["added_members"] = sorted(full_names)
        return result

    def _modify_member(self, name, path, old_code, new_code):
        """Change only the leading UPROPERTY/UFUNCTION annotation of one member."""
        if not name or "::" not in name or not path:
            raise SafeError("modify_member 必须提供完整限定名和头文件 path。")
        candidate = Path(self.root) / path
        p = Path(canonical(candidate))
        if candidate.is_symlink() or not p.is_file() or not inside(p, self.scope) or p.suffix.lower() not in HEADERS:
            raise SafeError("成员路径不在当前 scope 或不是普通头文件。")
        source = Source.load(str(p))
        occurrences = [o for o in source.occurrences if o.name == name and o.role == "declaration"]
        if len(occurrences) != 1 or occurrences[0].unsafe:
            raise SafeError("完整限定名在该头文件中不唯一或位于不支持的语法中。")
        occurrence = occurrences[0]
        if occurrence.kind not in {"variable", "function"}:
            raise SafeError("modify_member 只处理字段或函数声明。")
        symbol = SimpleNamespace(name=name, kind=occurrence.kind, file=str(p), bodyfile="")
        if not old_code.strip() or not new_code.strip():
            raise SafeError("成员标记修改需要完整的旧、新声明。")
        parents = [c for c in source.containers if c.kind in {"class", "struct"}
                   and c.open < occurrence.start < occurrence.end < c.close]
        if not parents:
            raise SafeError("成员声明不属于可编辑的 class/struct。")
        owner = max(parents, key=lambda c: c.open)
        if self.store.blocked(symbol.name, canonical(p), all_file=True) or self.store.blocked(owner.name, canonical(p), all_file=True):
            raise SafeError("成员、所在类型或源码已锁定。")
        if any(c.start < occurrence.end and c.end > occurrence.start for c in source.comments):
            raise SafeError("成员声明内含注释；先独立处理注释，不能随标记修改覆盖。")
        if any(d.start < occurrence.end and d.end > occurrence.start for d in source.directives):
            raise SafeError("成员声明跨越预处理指令，不能安全修改。")

        expected_macro = "UPROPERTY" if symbol.kind == "variable" else "UFUNCTION"
        leaf_name = symbol.name.rsplit("::", 1)[-1]
        payload_name = "__UEMCPMemberPayload"

        def member_payload(code, require_macro):
            tokens, comments, directives = lex(code)
            if comments or directives or not tokens:
                raise SafeError("成员声明不能包含注释或预处理指令。")
            token_pairs = pairs(tokens)
            if require_macro:
                if len(tokens) < 3 or tokens[0].value != expected_macro or tokens[1].value != "(":
                    raise SafeError(f"新声明必须以 {expected_macro}(...) 开始。")
                close = token_pairs.get(1)
                if close is None:
                    raise SafeError("反射标记括号不完整。")
                if sum(t.value == expected_macro for t in tokens[:close + 1]) != 1:
                    raise SafeError("新声明只能包含一个前置反射标记。")
                body = [t.value for t in tokens[close + 1:]]
            else:
                body = [t.value for t in tokens]
                if tokens[0].value == expected_macro and len(tokens) > 1 and tokens[1].value == "(":
                    close = token_pairs.get(1)
                    if close is None:
                        raise SafeError("旧反射标记括号不完整。")
                    body = [t.value for t in tokens[close + 1:]]
            wrapped = f"class {payload_name} {{\n{code}\n}};"
            parsed = Source.load(symbol.file, wrapped.encode("utf-8"))
            members = [o for o in parsed.occurrences if o.name == f"{payload_name}::{leaf_name}"]
            if (parsed.comments or parsed.directives or len(parsed.containers) != 1 or len(members) != 1
                    or members[0].kind != symbol.kind or members[0].role != "declaration" or members[0].unsafe):
                raise SafeError("载荷必须是一个完整、同类型的 class/struct 成员声明。")
            parsed_tokens = [t.value for t in parsed.tokens
                             if members[0].start <= t.start and t.end <= members[0].end]
            if parsed_tokens != [t.value for t in tokens]:
                raise SafeError("载荷含目标声明以外的代码。")
            return [t.value for t in tokens], body

        old_values, old_body = member_payload(old_code, False)
        new_values, new_body = member_payload(new_code, True)
        if old_body != new_body:
            raise SafeError("modify_member 只能增改 UPROPERTY/UFUNCTION 标记，不能修改字段类型、名称、默认值或函数签名。")
        actual = [t.value for t in source.tokens if occurrence.start <= t.start and t.end <= occurrence.end]
        if old_values != actual:
            raise SafeError("old_code 与当前成员声明不符；请重新读取后预览。")

        line_start = source.text.rfind("\n", 0, occurrence.start) + 1
        prefix = source.text[line_start:occurrence.start]
        indent = prefix[:len(prefix) - len(prefix.lstrip(" \t"))]
        newline = "\r\n" if "\r\n" in source.text else "\n"
        replacement = new_code.strip().replace("\r\n", "\n").replace("\r", "\n")
        replacement = replacement.replace("\n", newline + indent)
        text = source.text[:occurrence.start] + replacement + source.text[occurrence.end:]
        new_bytes = source.encode(text)
        check = Source.load(str(p), new_bytes)
        expected_topology = [item for item in self._token_topology(source) if item[0] != symbol.name]
        checked_topology = [item for item in self._token_topology(check) if item[0] != symbol.name]
        if checked_topology != expected_topology:
            raise SafeError("反射标记修改改变了目标以外的符号结构或 C++ 签名。")
        checked = [o for o in check.occurrences if o.name == symbol.name
                   and o.kind == symbol.kind and o.role == "declaration"]
        if len(checked) != 1:
            raise SafeError("修改后不能唯一解析回原成员。")
        check_values = [t.value for t in check.tokens if checked[0].start <= t.start and t.end <= checked[0].end]
        if check_values != new_values:
            raise SafeError("修改后成员声明与预览载荷不一致。")

        result = self._plan("Write", "code", symbol,
                            [(canonical(p), source.raw, new_bytes)],
                            {canonical(p): source.raw},
                            {canonical(p): (source.text, text)}, all_file=True)
        lock_names = [symbol.name, owner.name]
        self.plan.locks = [(item, canonical(p), True) for item in lock_names]
        result["locked"] = any(self.store.blocked(item, canonical(p), all_file=True) for item in lock_names)
        result["owner"] = owner.name
        result["modified_member"] = symbol.name
        result["reflection_macro"] = expected_macro
        return result

    def _modify_members(self, name, path, members):
        """Apply UPROPERTY-only changes to several existing fields in one transaction."""
        if not isinstance(members, list) or not 1 <= len(members) <= 50:
            raise SafeError("modify_members 需要 1..50 个成员声明。")
        if not name or "::" not in name or not path:
            raise SafeError("modify_members 必须提供完整限定名和头文件 path。")
        candidate = Path(self.root) / path
        p = Path(canonical(candidate))
        if candidate.is_symlink() or not p.is_file() or not inside(p, self.scope) or p.suffix.lower() not in HEADERS:
            raise SafeError("成员路径不在当前 scope 或不是普通头文件。")
        source = Source.load(str(p))
        anchors = [o for o in source.occurrences if o.name == name
                   and o.kind == "variable" and o.role == "declaration"]
        if len(anchors) != 1 or anchors[0].unsafe:
            raise SafeError("Target 字段不唯一或位于不支持的语法中。")
        anchor_occurrence = anchors[0]
        parents = [c for c in source.containers if c.kind in {"class", "struct"}
                   and c.open < anchor_occurrence.start < anchor_occurrence.end < c.close]
        if not parents:
            raise SafeError("Target 字段不属于可编辑的 class/struct。")
        owner = max(parents, key=lambda c: c.open)
        anchor = SimpleNamespace(name=name, kind="variable", file=str(p), bodyfile="")

        changes, wanted_values, full_names = [], {}, set()
        for item in members:
            if not isinstance(item, dict) or set(item) != {"name", "old_code", "new_code"}:
                raise SafeError("每个成员项必须只含 name、old_code、new_code。")
            member_name = item["name"].strip()
            if not member_name:
                raise SafeError("成员名称不能为空。")
            full_name = member_name if "::" in member_name else owner.name + "::" + member_name
            if full_name.rpartition("::")[0] != owner.name or full_name in full_names:
                raise SafeError("成员必须属于同一目标类型且不能重复。")
            occurrences = [o for o in source.occurrences if o.name == full_name
                           and o.kind == "variable" and o.role == "declaration"]
            if len(occurrences) != 1 or occurrences[0].unsafe:
                raise SafeError("字段声明不唯一或位于不支持的语法中。")
            if self.store.blocked(full_name, canonical(p), all_file=True):
                raise SafeError("批量操作只接受同一头文件中未锁定的字段。")
            occurrence = occurrences[0]
            if any(c.start < occurrence.end and c.end > occurrence.start for c in source.comments):
                raise SafeError("字段声明内含注释；先独立处理注释，不能随标记修改覆盖。")
            if any(d.start < occurrence.end and d.end > occurrence.start for d in source.directives):
                raise SafeError("字段声明跨越预处理指令，不能安全修改。")

            old_tokens, old_comments, old_directives = lex(item["old_code"])
            new_tokens, new_comments, new_directives = lex(item["new_code"])
            if old_comments or old_directives or new_comments or new_directives or not old_tokens or not new_tokens:
                raise SafeError("字段声明不能包含注释或预处理指令。")
            old_pairs, new_pairs = pairs(old_tokens), pairs(new_tokens)
            if len(new_tokens) < 3 or new_tokens[0].value != "UPROPERTY" or new_tokens[1].value != "(":
                raise SafeError("每个新字段声明必须以 UPROPERTY(...) 开始。")
            new_close = new_pairs.get(1)
            if new_close is None or sum(t.value == "UPROPERTY" for t in new_tokens[:new_close + 1]) != 1:
                raise SafeError("新字段必须只有一个前置 UPROPERTY 标记。")
            new_body = [t.value for t in new_tokens[new_close + 1:]]
            old_body = [t.value for t in old_tokens]
            if old_tokens[0].value == "UPROPERTY" and len(old_tokens) > 1 and old_tokens[1].value == "(":
                old_close = old_pairs.get(1)
                if old_close is None:
                    raise SafeError("旧 UPROPERTY 标记括号不完整。")
                old_body = [t.value for t in old_tokens[old_close + 1:]]
            if old_body != new_body:
                raise SafeError("modify_members 只能修改 UPROPERTY 标记，不能修改字段类型、名称或默认值。")
            actual = [t.value for t in source.tokens if occurrence.start <= t.start and t.end <= occurrence.end]
            old_values = [t.value for t in old_tokens]
            if actual != old_values:
                raise SafeError("old_code 与当前字段声明不符；请重新读取后预览。")

            payload = f"class __UEMCPMemberPayload {{\n{item['new_code']}\n}};"
            parsed = Source.load(str(p), payload.encode("utf-8"))
            parsed_members = [o for o in parsed.occurrences if o.name == "__UEMCPMemberPayload::" + full_name.rsplit("::", 1)[-1]]
            if (parsed.comments or parsed.directives or len(parsed.containers) != 1 or len(parsed_members) != 1
                    or parsed_members[0].kind != "variable" or parsed_members[0].role != "declaration"
                    or parsed_members[0].unsafe):
                raise SafeError("new_code 必须解析为单个完整字段声明。")
            parsed_values = [t.value for t in parsed.tokens
                             if parsed_members[0].start <= t.start and t.end <= parsed_members[0].end]
            if parsed_values != [t.value for t in new_tokens]:
                raise SafeError("new_code 含目标字段以外的代码。")

            line_start = source.text.rfind("\n", 0, occurrence.start) + 1
            prefix = source.text[line_start:occurrence.start]
            indent = prefix[:len(prefix) - len(prefix.lstrip(" \t"))]
            newline = "\r\n" if "\r\n" in source.text else "\n"
            replacement = item["new_code"].strip().replace("\r\n", "\n").replace("\r", "\n")
            replacement = replacement.replace("\n", newline + indent)
            changes.append((occurrence.start, occurrence.end, replacement))
            wanted_values[full_name] = [t.value for t in new_tokens]
            full_names.add(full_name)

        if self.store.blocked(owner.name, canonical(p), all_file=True):
            raise SafeError("所在类型或源码已锁定。")
        text = source.text
        for start, end, replacement in sorted(changes, key=lambda change: change[0], reverse=True):
            text = text[:start] + replacement + text[end:]
        new_bytes = source.encode(text)
        check = Source.load(str(p), new_bytes)
        before_topology = [item for item in self._token_topology(source) if item[0] not in full_names]
        after_topology = [item for item in self._token_topology(check) if item[0] not in full_names]
        if after_topology != before_topology:
            raise SafeError("批量标记修改改变了目标范围以外的符号结构。")
        for full_name, values in wanted_values.items():
            updated = [o for o in check.occurrences if o.name == full_name
                       and o.kind == "variable" and o.role == "declaration"]
            if len(updated) != 1:
                raise SafeError("修改后不能唯一解析回原字段。")
            actual = [t.value for t in check.tokens if updated[0].start <= t.start and t.end <= updated[0].end]
            if actual != values:
                raise SafeError("修改后字段声明与预览载荷不一致。")

        result = self._plan("Write", "code", anchor,
                            [(canonical(p), source.raw, new_bytes)],
                            {canonical(p): source.raw},
                            {canonical(p): (source.text, text)}, all_file=True)
        lock_names = [anchor.name, owner.name, *sorted(full_names)]
        self.plan.locks = [(item, canonical(p), True) for item in lock_names]
        result["locked"] = any(self.store.blocked(item, canonical(p), all_file=True) for item in lock_names)
        result["owner"] = owner.name
        result["modified_members"] = sorted(full_names)
        result["reflection_macro"] = "UPROPERTY"
        return result

    @staticmethod
    def _token_topology(source):
        return [(o.name, o.kind, o.role, o.args, commentless(source.text[o.start:o.signature_end]) if o.kind == "function" else "") for o in source.occurrences]

    def delete(self, *args, **kwargs):
        result = self._delete(*args, **kwargs)
        if result.get("status") == "preview":
            from .approvals import register
            result["approval"] = register(self)
        return result

    def _delete(self, action="preview", kind="code", old_code="", part="body", comment_id="", reason="", preview_id="", document_id="", name="", path=""):
        if action == "apply":
            if old_code or comment_id or document_id or name or path:
                raise SafeError("Delete Apply 只接受已有 preview_id。")
            return self._apply("Delete", preview_id)
        self.plan = None
        if action != "preview" or not reason.strip():
            raise SafeError("删除必须独立 preview，并填写具体 reason；reason 不是身份验证。")
        if kind == "include":
            from .maintenance import edit_include
            return edit_include(self,path,name,old_code,"",delete=True,reason=reason)
        if document_id:
            if name or path:
                raise SafeError("document_id 与 name/path 不能同时指定。")
            if kind != "documentation" or not re.fullmatch(r"[0-9a-f]{20}", document_id):
                raise SafeError("document_id 只能明确定位独立文档；必须是 docs_status 返回的20位ID。")
            self.catalog.ensure()
            p = self.catalog.docs_dir / (document_id + ".dox")
            if not p.is_file() or p.is_symlink() or not inside(p, self.root):
                raise SafeError("独立文档不存在或越界。")
            raw = p.read_bytes()
            first, _, body = raw.decode("utf-8-sig").partition("\n")
            if not first.startswith(DOC_PREFIX):
                raise SafeError("不是受管文档。")
            meta = json.loads(first[len(DOC_PREFIX):])
            if meta.get("target_id") != document_id or not isinstance(meta.get("name"), str):
                raise SafeError("文档身份不匹配。")
            source_path = canonical(Path(self.root) / meta.get("declaration_file", ""))
            if not inside(source_path, self.root):
                raise SafeError("文档关联源码越界。")
            r = self._plan("Delete", kind, None, [(canonical(p), raw, None)], {},
                           {canonical(p): (clean_comment(body), "")}, reason)
            self.plan.locks = [(meta["name"], source_path, False)]
            r["locked"] = bool(self.store.blocked(meta["name"], source_path))
            r["document_id"] = document_id
            return r
        s = self._symbol(name, path)
        if kind == "documentation":
            meta, text = self._doc(s)
            p = self._doc_path(s)
            if meta is None:
                raise SafeError("没有可删除的外置文档。")
            return self._plan("Delete", kind, s, [(canonical(p), p.read_bytes(), None)], self._linked(s),
                              {canonical(p): (text, "")}, reason)
        items = self.guard._current()
        changes, fragments = [], {}
        if kind == "symbol":
            sources = {o.path: self.guard._source(o) for o in items}
            for o in items:
                source = sources[o.path]
                if source.leading(o) or any(o.start <= c.start < o.end or (c.start >= o.end and not source.text[o.end:c.start].strip() and "\n" not in source.text[o.end:c.start]) for c in source.comments):
                    raise SafeError("符号携带源码注释；先用独立注释操作处理，不能通过删代码隐式删文档。外置 .dox 将保留为孤立文档。")
            for path, source in sources.items():
                spans = sorted([(o.start, o.end) for o in items if o.path == path], reverse=True)
                text = source.text
                removed = []
                for start, end in spans:
                    removed.append(text[start:end])
                    text = text[:start] + text[end:]
                check = Source.load(path, source.encode(text))
                expected = [x for x in self._token_topology(source) if x[0] != s.name]
                if self._token_topology(check) != expected:
                    raise SafeError("符号删除影响了其他对象。")
                changes.append((path, source.raw, source.encode(text)))
                fragments[path] = ("\n".join(reversed(removed)), "")
        elif kind in {"code", "comment"}:
            facet = "code" if kind == "code" else part
            self.guard.prepare(facet)
            ticket = self.guard.ticket
            source = Source.load(ticket["path"], ticket["sources"][ticket["path"]])
            replacement = ""
            if kind == "comment":
                _, _, comments = self.guard._comments(items, part)
                chosen = [c for c in comments if sha((source.revision + str(c.start)).encode())[:12] == comment_id]
                if len(chosen) != 1:
                    raise SafeError("删除注释必须指定唯一 comment_id。")
                c = chosen[0]
                start, end = c.start, c.end
                replacement = "".join(ch if ch in "\r\n" else " " for ch in c.value)
            else:
                wanted, comments, dirs = lex(old_code)
                wanted = sorted(wanted + dirs, key=lambda x: x.start)
                if not wanted or comments:
                    raise SafeError("代码删除需要非空且不含注释的唯一片段。")
                pairs(wanted)
                body = sorted((t for t in source.tokens + source.directives if ticket["start"] <= t.start and t.end <= ticket["end"]), key=lambda x: x.start)
                vals, wvals = [t.value for t in body], [t.value for t in wanted]
                matches = [i for i in range(len(vals)-len(wvals)+1) if vals[i:i+len(wvals)] == wvals]
                if len(matches) != 1:
                    raise SafeError("删除片段未找到或不唯一。")
                start, end = body[matches[0]].start, body[matches[0]+len(wvals)-1].end
                if any(c.start < end and c.end > start for c in source.comments):
                    raise SafeError("不能通过代码删除跨越注释。")
            text = source.text[:start] + replacement + source.text[end:]
            check = Source.load(source.path, source.encode(text))
            expected_tokens = [t.value for t in source.tokens if kind == "comment" or t.end <= start or t.start >= end]
            if [t.value for t in check.tokens] != expected_tokens or self._token_topology(check) != self._token_topology(source):
                raise SafeError("删除改变了范围外 token、签名或符号结构。")
            changes = [(source.path, source.raw, source.encode(text))]
            fragments[source.path] = (source.text[start:end], replacement)
        else:
            raise SafeError("Delete kind 为 code/comment/documentation/symbol。")
        return self._plan("Delete", kind, s, changes, self._linked(s), fragments, reason, all_file=kind == "comment" and part == "file_header")

    def configure(self, action="status", name="", path="", settings=None, reason="", public_only=True, output_format="html", limit=50, changed_only=False, base="HEAD"):
        if action == "policy":
            from . import policy
            p=policy.load(self.store,self.root)
            b=policy.metadata(self.store,self.root,'baseline')
            return {"policy":p,"policy_hash":policy.digest(p),"baseline_valid":bool(b and b["policy_hash"]==policy.digest(p)),
                    "user_only":["import_policy","accept_baseline"]}
        if action == "approvals":
            from .approvals import pending
            rows=pending(self.store,self.root)
            return {"requests":[{"preview_id":r["id"],"state":r["status"],"target":r["plan"]["target"],"reason":r["plan"]["reason"]} for r in rows[:limit]],"total":len(rows)}
        if action == "release":
            if path or changed_only: raise SafeError("正式发布使用用户批准规则的全项目范围，不能通过path/scope/changed_only缩小。")
            from .quality import release
            return release(self,output_format)
        if action == "last_release":
            from . import policy
            r=policy.metadata(self.store,self.root,'last_release')
            if not r:return {"status":"never_released"}
            from .quality import source_snapshot
            return {k:v for k,v in r.items() if k!='source_snapshot'} | {"source_current":r['source_snapshot']==source_snapshot(self),"policy_current":r['policy_hash']==policy.digest(policy.load(self.store,self.root))}
        if action == "abort":
            return self.abort()
        if action == "status":
            return {"project": self.root, "scope": os.path.relpath(self.scope, self.root), "target": self.default_locator,
                    "container": self.container,
                    "doxygen_version": self.catalog.version or "not_checked", "build": self.catalog.last_build,
                    "session": self.session, "tools": ["Read", "Write", "Delete", "Configure"],
                    "state_database": str(self.store.path)}
        if action == "target":
            symbol = self._resolve_symbol(name, path)
            self._select(symbol)
            return {**self.configure(), "name": symbol.name, "locked": self._locked(symbol)}
        if action == "parent":
            self.abort()
            if self.target:
                self.target, self.default_locator = None, None
            else:
                self.container = self.container.rpartition("::")[0]
            return self.configure()
        if action == "child":
            self.catalog.ensure()
            dest = "::".join(filter(None, [self.container, name])) if name else self.remembered.get(self.container, "")
            matches = self._path_filter([s for s in self.catalog.symbols if s.id == dest or s.name == dest])
            if len(matches) == 1:
                self._select(matches[0])
            elif any(s.name.startswith(dest + "::") for s in self.catalog.symbols) and dest:
                self.abort()
                self.container, self.target, self.default_locator = dest, None, None
            else:
                raise SafeError("此层没有唯一子项/记忆；请搜索。")
            return self.configure()
        if action == "scope":
            p = canonical(Path(self.root) / path)
            if not Path(p).is_dir() or not inside(p, self.root):
                raise SafeError("scope 必须是启动项目内目录；不能改变安全根目录。")
            self.abort()
            self.scope, self.target, self.default_locator, self.container = p, None, None, ""
            self.guard.scope = p
            return self.configure()
        if action == "validate":
            if not self.validator:
                return {"status": "not_configured", "message": "启动时用 --validation-profile 指定用户信任的编译/测试命令。"}
            return self.validator.run(self.root)
        if action == "reindex":
            self.abort()
            self.catalog.ensure(force=True)
            return self.catalog.last_build
        if action == "check_comments":
            from .doc_pipeline import check_comments
            return check_comments(self, path, public_only, limit, changed_only=changed_only, base=base)
        if action == "export_docs":
            from .doc_pipeline import export_docs
            return export_docs(self, path, output_format, public_only)
        if action == "build_docs":
            self.abort()
            return self.catalog.build(html=True)
        if action == "set":
            self.catalog.validate_settings(settings)
            p = self.catalog.settings_file
            if p.is_symlink() or not inside(p, self.root):
                raise SafeError("配置文件路径越界。")
            self.abort()
            dump_atomic(p, settings)
            self.catalog.fingerprint = ""
            self.catalog.load_settings()
            return {"settings": self.catalog.settings, "index_stale": True}
        if action in {"lock", "lock_status"}:
            s = self._symbol(name, path)
            if action == "lock":
                self.store.lock(self.root, s.name, [{"name": s.name, "path": p} for p in self._linked(s)], reason)
                self.abort()
            return {"target": self._locator(s), "name": s.name, "locked": self._locked(s)}
        if action == "docs_status":
            self.catalog.ensure()
            existing = {s.id for s in self.catalog.symbols}
            docs = []
            for p in self.catalog.docs_dir.glob("*.dox"):
                try:
                    meta = json.loads(p.read_text(encoding="utf-8").splitlines()[0][len(DOC_PREFIX):])
                    docs.append({"name": meta["name"], "document_id": meta["target_id"], "orphan": meta["target_id"] not in existing,
                                 "file": os.path.relpath(p, self.root)})
                except (OSError, ValueError, KeyError, IndexError):
                    docs.append({"file": os.path.relpath(p, self.root), "error": "unmanaged_or_invalid"})
            return {"documents": docs[:100], "total": len(docs), "truncated": len(docs)>100}
        raise SafeError("未知配置动作；不存在 MCP 解锁动作。")
