"""Conservative, offset-preserving C++ subset index. No regex whole-file fallback.

This is deliberately not a C++ compiler. Ambiguous/unsupported locations fail
closed. The lexer understands comments, escaped/prefixed/raw literals and keeps
Unicode character offsets; writes re-encode strict UTF-8 and preserve the BOM.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_cpp


_CPP_LANGUAGE = Language(tree_sitter_cpp.language())
_PARSERS = threading.local()


def variable_name(declaration: str) -> str | None:
    """Parse one declaration, without headers, type resolution or a project AST."""
    if not hasattr(_PARSERS, "cpp"):
        _PARSERS.cpp = Parser(_CPP_LANGUAGE)
    data = ("struct MemberProbe {\n" + declaration + "\n};").encode("utf-8")
    root = _PARSERS.cpp.parse(data).root_node
    if root.has_error or len(root.named_children) != 1:
        return None
    owner = root.named_children[0]
    if owner.type != "struct_specifier":
        return None
    body = owner.child_by_field_name("body")
    if body is None or len(body.named_children) != 1:
        return None
    field = body.named_children[0]
    if field.type != "field_declaration":
        return None
    declarators = field.children_by_field_name("declarator")
    if len(declarators) != 1:
        return None
    node = declarators[0]
    while node.type in {"pointer_declarator", "reference_declarator", "array_declarator"}:
        node = node.child_by_field_name("declarator")
        if node is None:
            return None
    if node.type not in {"identifier", "field_identifier", "qualified_identifier"}:
        return None
    return data[node.start_byte:node.end_byte].decode("utf-8")


class SafeError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    kind: str = "token"


IDENT = re.compile(r"[A-Za-z_]\w*")
NUMBER = re.compile(r"(?:0[xX][0-9a-fA-F']+(?:\.[0-9a-fA-F']*)?(?:[pP][+-]?\d+)?|0[bB][01']+|(?:\d[\d']*)(?:\.\d*)?(?:[eE][+-]?\d+)?)[A-Za-z0-9_]*")
LITERAL = re.compile(r'(?:u8|u|U|L)?(R)?([\"\'])')
OPS = sorted("<=> <<= >>= ->* ... :: -> ++ -- == != <= >= && || += -= *= /= %= &= |= ^= << >> .* ##".split(), key=len, reverse=True)
ANNOTATIONS = {"UFUNCTION", "UPROPERTY", "UCLASS", "USTRUCT", "UENUM", "UINTERFACE", "GENERATED_BODY", "GENERATED_UCLASS_BODY", "UE_DEPRECATED", "UE_NODISCARD", "UE_REQUIRES", "alignas", "__declspec", "IMPLEMENT_MODULE"}
SKIP_FUNCTIONS = ANNOTATIONS | {"if", "for", "while", "switch", "catch", "sizeof", "alignof", "decltype", "noexcept", "static_assert", "requires"}
EXTENSIONS = {".h", ".hpp", ".hh", ".hxx", ".cpp", ".cc", ".cxx", ".inl", ".c"}
HEADERS = {".h", ".hpp", ".hh", ".hxx"}
EXCLUDED = {".git", ".vs", ".idea", ".agent", ".agents", ".doxygenue", "upstream", "vendor", "tools", "docs", "evidence", "tests", ".venv", "venv", "node_modules", "Binaries", "DerivedDataCache", "Intermediate", "Saved", "Content", "__pycache__"}


def canonical(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def inside(path: str | Path, root: str | Path) -> bool:
    try:
        return os.path.commonpath([canonical(path), canonical(root)]) == canonical(root)
    except ValueError:
        return False


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lex(source: str) -> tuple[list[Token], list[Token], list[Token]]:
    tokens, comments, directives = [], [], []
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if c.isspace():
            i += 1
            continue
        if source.startswith("\\\n", i) or source.startswith("\\\r\n", i):
            raise SafeError("不支持代码行拼接；无法安全定位。")
        if c == "#" and not source[source.rfind("\n", 0, i) + 1:i].strip():
            end = source.find("\n", i)
            end = n if end < 0 else end
            while source[i:end].rstrip("\r").endswith("\\") and end < n:
                next_end = source.find("\n", end + 1)
                end = n if next_end < 0 else next_end
            if end > i and source[end - 1] == "\r":
                end -= 1
            directives.append(Token(source[i:end], i, end, "directive"))
            i = end
            continue
        if source.startswith("//", i):
            end = source.find("\n", i)
            end = n if end < 0 else end
            if source[i:end].rstrip("\r").endswith("\\"):
                raise SafeError("不支持带行拼接的 // 注释。")
            if end > i and source[end - 1] == "\r":
                end -= 1
            comments.append(Token(source[i:end], i, end, "line"))
            i = end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end < 0:
                raise SafeError("注释未闭合。")
            end += 2
            comments.append(Token(source[i:end], i, end, "block"))
            i = end
            continue
        literal = LITERAL.match(source, i)
        if literal:
            raw, quote = literal.groups()
            if raw:
                if quote != '"':
                    raise SafeError("无效的 raw literal。")
                begin = source.find("(", literal.end())
                delimiter = source[literal.end():begin] if begin >= 0 else " " * 17
                if len(delimiter) > 16 or re.search(r"[\s()\\]", delimiter):
                    raise SafeError("Raw literal 分隔符无法安全解析。")
                suffix = ")" + delimiter + '"'
                end = source.find(suffix, begin + 1)
                if end < 0:
                    raise SafeError("Raw literal 未闭合。")
                end += len(suffix)
            else:
                end = literal.end()
                while end < n and source[end] != quote:
                    if source[end] in "\r\n":
                        raise SafeError("普通字符串包含未转义换行。")
                    end += 2 if source[end] == "\\" else 1
                if end >= n:
                    raise SafeError("字符串未闭合。")
                end += 1
            # Preserve user-defined literal suffix as part of the same token.
            suffix_match = IDENT.match(source, end)
            if suffix_match:
                end = suffix_match.end()
            tokens.append(Token(source[i:end], i, end, "literal"))
            i = end
            continue
        match = NUMBER.match(source, i) or IDENT.match(source, i)
        if match:
            end = match.end()
        else:
            op = next((op for op in OPS if source.startswith(op, i)), c)
            end = i + len(op)
        tokens.append(Token(source[i:end], i, end))
        i = end
    return tokens, comments, directives


def pairs(tokens: list[Token]) -> dict[int, int]:
    stack, result = [], {}
    for i, token in enumerate(tokens):
        if token.kind == "literal":
            continue
        v = token.value
        if v in {"(", "[", "{"}:
            stack.append(i)
        elif v in {")", "]", "}"}:
            if not stack or tokens[stack[-1]].value != {")": "(", "]": "[", "}": "{"}[v]:
                raise SafeError("括号不平衡；拒绝猜测范围（可能是条件编译或宏）。")
            j = stack.pop()
            result[i], result[j] = j, i
    if stack:
        raise SafeError("括号未闭合；拒绝猜测范围。")
    return result


def clean_comment(raw: str) -> str:
    if raw.startswith("//"):
        return re.sub(r"^//[/!]?[ \t]?", "", raw).strip()
    body = re.sub(r"^/\*[*!]?", "", raw)
    body = re.sub(r"\*/$", "", body)
    return "\n".join(re.sub(r"^\s*\* ?", "", line).rstrip() for line in body.splitlines()).strip()


def commentless(source: str) -> str:
    _, comments, _ = lex(source)
    out, last = [], 0
    for c in comments:
        out.append(source[last:c.start])
        # Spaces, not deletion: int/**/x must never become intx.
        out.append("".join("\n" if ch == "\n" else " " for ch in c.value))
        last = c.end
    out.append(source[last:])
    return "\n".join(line.rstrip() for line in "".join(out).splitlines() if line.strip()).strip()


def argument_key(tokens: list[Token]) -> str:
    """Conservative parameter normalization; unknown complex forms stay distinct."""
    parts, part, depth = [], [], 0
    for token in tokens + [Token(",", 0, 0)]:
        v = token.value
        if v in {"(", "[", "<"}:
            depth += 1
        elif v in {")", "]", ">"}:
            depth -= 1
        elif v == ">>":
            depth -= 2
        if v == "," and depth == 0:
            # UPARAM is declaration-only UE metadata, not a C++ parameter type.
            if len(part)>2 and part[:2]==["UPARAM","("]:
                balance=1;j=2
                while j<len(part) and balance:
                    balance += (part[j]=="(") - (part[j]==")");j+=1
                part=part[j:]
            if "=" in part:
                part = part[:part.index("=")]
            if len(part) > 1 and IDENT.fullmatch(part[-1]) and part[-2] != "::" and part[-1] not in {"int", "long", "short", "char", "double", "float", "bool", "void", "unsigned", "signed", "const"}:
                part = part[:-1]
            if "*" not in part and "&" not in part and "&&" not in part:
                part=[v for v in part if v not in {"const", "volatile"}]
            parts.append(" ".join(part))
            part = []
        else:
            part.append(v)
    return ",".join(parts)


@dataclass
class Occurrence:
    path: str
    name: str
    kind: str
    role: str
    start: int
    end: int
    signature_end: int
    open: int | None = None
    close: int | None = None
    args: str = ""
    unsafe: bool = False


@dataclass
class Container:
    name: str
    kind: str
    start: int
    open: int
    close: int
    templated: bool = False


@dataclass
class Source:
    path: str
    raw: bytes
    text: str
    bom: bool
    tokens: list[Token]
    comments: list[Token]
    directives: list[Token]
    occurrences: list[Occurrence] = field(default_factory=list)
    containers: list[Container] = field(default_factory=list)

    @classmethod
    def load(cls, path: str, raw: bytes | None = None) -> "Source":
        raw = Path(path).read_bytes() if raw is None else raw
        text = raw.decode("utf-8-sig", errors="strict")
        ts, cs, ds = lex(text)
        source = cls(canonical(path), raw, text, raw.startswith(b"\xef\xbb\xbf"), ts, cs, ds)
        source._parse()
        return source

    @property
    def revision(self) -> str:
        return sha(self.raw)

    def encode(self, text: str) -> bytes:
        return (b"\xef\xbb\xbf" if self.bom else b"") + text.encode("utf-8")

    def leading(self, occurrence: Occurrence) -> list[Token]:
        end, selected = occurrence.start, []
        for comment in reversed(self.comments):
            if comment.end > end:
                continue
            gap = self.text[comment.end:end]
            if gap.strip() or gap.count("\n") > 1 or "@file" in comment.value:
                break
            # Do not steal a preceding function's trailing comment.
            line_prefix = self.text[self.text.rfind("\n", 0, comment.start) + 1:comment.start]
            if line_prefix.strip():
                break
            selected.append(comment)
            end = comment.start
        return list(reversed(selected))

    def file_header(self) -> list[Token]:
        stop = min([t.start for t in self.tokens[:1]] + [d.start for d in self.directives[:1]] + [len(self.text)])
        has_directive_before_code = bool(self.directives and self.directives[0].start == stop)
        return [c for c in self.comments if c.end <= stop and (has_directive_before_code or "@file" in c.value or self.text[c.end:stop].count("\n") >= 2)]

    def _parse(self) -> None:
        ts, pm = self.tokens, pairs(self.tokens)
        def function_info(a: int, b: int, context: list[str]):
            k = a
            while k < b:
                value = ts[k].value
                if value == "[":
                    k = pm[k] + 1
                    continue
                if value == "(":
                    prev = ts[k - 1].value if k > a else ""
                    if prev in SKIP_FUNCTIONS:
                        k = pm[k] + 1
                        continue
                    if not IDENT.fullmatch(prev):
                        return None
                    name_start = k - 1
                    if name_start > a and ts[name_start - 1].value == "~":
                        name_start -= 1
                    while name_start - 2 >= a and ts[name_start - 1].value == "::" and IDENT.fullmatch(ts[name_start - 2].value):
                        name_start -= 2
                    local = "".join(t.value for t in ts[name_start:k])
                    # A bare call / macro invocation at namespace scope isn't a declaration.
                    if name_start == a and "::" not in local and (not context or local.lstrip("~") != context[-1]):
                        return None
                    prefix_start = a
                    while prefix_start + 1 < name_start and ts[prefix_start].value in ANNOTATIONS and ts[prefix_start + 1].value == "(":
                        prefix_start = pm[prefix_start + 1] + 1
                    prefix = [t.value for t in ts[prefix_start:name_start]]
                    if any(v in prefix for v in ["=", "return", "typedef", "using", "operator"]):
                        return None
                    if any(t.value == "operator" for t in ts[a:b]):
                        return None
                    qualified = "::".join(context + [local]) if context and not local.startswith("::".join(context) + "::") else local
                    arg_end = pm[k]
                    tail = [t.value for t in ts[arg_end + 1:b]]
                    # Constructor initializer lists and requires expressions need a real parser.
                    unsupported = ":" in tail or "try" in tail or "requires" in tail
                    return qualified, argument_key(ts[k + 1:arg_end]), unsupported
                if value in {"{", ";", "="}:
                    break
                k += 1
            return None

        def variable_info(a: int, b: int, context: list[str]):
            if a >= b:
                return None
            # Strip leading UE property annotations.
            k = a
            while k + 1 < b and ts[k].value in ANNOTATIONS and ts[k + 1].value == "(":
                k = pm[k + 1] + 1
            if k >= b:
                return None
            local = variable_name(self.text[ts[k].start:ts[b].start] + ";")
            if local is None:
                return None
            name = "::".join(context + [local]) if context and not local.startswith("::".join(context) + "::") else local
            return name

        def block(begin: int, end: int, context: list[str], inherited_unsafe=False):
            a = i = begin
            while i < end:
                v = ts[i].value
                if v in {"public", "protected", "private"} and i + 1 < end and ts[i + 1].value == ":":
                    a = i = i + 2
                    continue
                if v in ANNOTATIONS and i + 1 < end and ts[i + 1].value == "(":
                    i = pm[i + 1] + 1
                    if v not in {"UFUNCTION", "UPROPERTY"}:
                        a = i
                    continue
                if v in {"(", "["}:
                    i = pm[i] + 1
                    continue
                if v == "{":
                    segment = ts[a:i]
                    values = [t.value for t in segment]
                    container = None
                    # A container must start with its keyword (plus inline or template).
                    if values and values[0] in {"namespace", "class", "struct", "union", "inline", "template"} and "(" not in values:
                        for key in ["namespace", "class", "struct", "union"]:
                            if key in values:
                                tail = values[values.index(key) + 1:]
                                if ":" in tail:
                                    tail = tail[:tail.index(":")]
                                tail = [x for x in tail if x != "final"]
                                if key == "namespace":
                                    container = "".join(tail) or "<anonymous>"
                                else:
                                    names = [x for x in tail if IDENT.fullmatch(x)]
                                    container = names[-1] if names else None
                                break
                    closing = pm[i]
                    if container:
                        self.containers.append(Container("::".join(context + container.split("::")), key, ts[a].start, ts[i].start, ts[closing].start, "template" in values))
                        block(i + 1, closing, context + container.split("::"), inherited_unsafe)
                    else:
                        info = function_info(a, i, context)
                        if info:
                            name, args, unsafe = info
                            self.occurrences.append(Occurrence(self.path, name, "function", "definition", ts[a].start, ts[closing].end, ts[i].start, ts[i].start, ts[closing].start, args, inherited_unsafe or unsafe))
                    i = closing + 1
                    if i < end and ts[i].value == ";":
                        i += 1
                    a = i
                    continue
                if v == ";":
                    if a < i:
                        info = function_info(a, i, context)
                        if info:
                            name, args, unsafe = info
                            self.occurrences.append(Occurrence(self.path, name, "function", "declaration", ts[a].start, ts[i].end, ts[i].end, args=args, unsafe=inherited_unsafe or unsafe))
                        else:
                            name = variable_info(a, i, context)
                            if name:
                                role = "declaration" if Path(self.path).suffix.lower() in HEADERS else "definition"
                                self.occurrences.append(Occurrence(self.path, name, "variable", role, ts[a].start, ts[i].end, ts[i].end, unsafe=inherited_unsafe))
                    a = i = i + 1
                    continue
                i += 1
        block(0, len(ts), [])


class Index:
    def __init__(self, root: str):
        self.root = canonical(root)
        self.sources: dict[str, Source] = {}
        self.stamps = {}
        self.groups: dict[str, list[Occurrence]] = {}
        self.errors: dict[str, str] = {}
        self.failed_text: dict[str, str] = {}
        self.incomplete = False

    def refresh(self) -> None:
        seen, count = set(), 0
        self.incomplete = False
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not Path(directory, d).is_symlink())
            for filename in sorted(files):
                path = Path(directory, filename)
                if path.suffix.lower() not in EXTENSIONS or path.is_symlink() or filename.endswith(".generated.h") or filename.endswith(".gen.cpp"):
                    continue
                count += 1
                if count > 20000:
                    self.incomplete = True
                    break
                key = canonical(path)
                if not inside(key, self.root):
                    continue
                seen.add(key)
                try:
                    stat = path.stat()
                    stamp = (stat.st_mtime_ns, stat.st_size)
                    if self.stamps.get(key) == stamp:
                        continue
                    self.sources.pop(key, None)
                    self.errors.pop(key, None)
                    self.failed_text.pop(key, None)
                    if stat.st_size > 2 * 1024 * 1024:
                        self.incomplete = True
                        raise SafeError("文件超过 2 MiB 安全上限。")
                    raw = path.read_bytes()
                    self.failed_text[key] = raw.decode("utf-8-sig", errors="replace")
                    self.sources[key] = Source.load(key, raw)
                    self.failed_text.pop(key, None)
                    self.stamps[key] = stamp
                except (OSError, UnicodeError, SafeError) as exc:
                    self.errors[key] = str(exc)
                    if isinstance(exc, OSError):
                        # An unreadable source may hide an overload; no proof of uniqueness.
                        self.incomplete = True
            if self.incomplete and count > 20000:
                break
        for key in (set(self.stamps) | set(self.sources) | set(self.errors) | set(self.failed_text)) - seen:
            self.stamps.pop(key, None)
            self.sources.pop(key, None)
            self.errors.pop(key, None)
            self.failed_text.pop(key, None)
        self.groups = {}
        for source in self.sources.values():
            for occurrence in source.occurrences:
                self.groups.setdefault(occurrence.name, []).append(occurrence)

    @staticmethod
    def ambiguous(items: list[Occurrence]) -> bool:
        return (len({o.kind for o in items}) != 1 or
                any(sum(o.role == role for o in items) > 1 for role in {"definition", "declaration"}) or
                (items[0].kind == "function" and len({o.args for o in items}) > 1))

    def resolve(self, name: str) -> list[Occurrence]:
        if self.incomplete:
            raise SafeError("索引不完整，不能证明 Target 唯一；缩小启动项目范围后重试。")
        items = self.groups.get(name, [])
        if not items:
            raise SafeError("Target 未找到；请搜索候选。不会退回整文件。")
        if self.ambiguous(items):
            raise SafeError("重载、重复定义或声明/定义不一致，无法唯一定位；拒绝读取/编辑。")
        leaf = name.rsplit("::", 1)[-1]
        # Detect unindexed same-leaf declarations (e.g. unknown annotation macros).
        # False negatives are worse than a conservative refusal in a code editor.
        for source in self.sources.values():
            for position, token in enumerate(source.tokens):
                if token.value != leaf or any(o.start <= token.start < o.end for o in source.occurrences):
                    continue
                if items[0].kind == "variable" or (position + 1 < len(source.tokens) and source.tokens[position + 1].value == "("):
                    raise SafeError("发现未安全解析的同名符号/引用，不能证明唯一定位。")
        if any(re.search(r"\b" + re.escape(leaf) + r"\b", text) for text in self.failed_text.values()):
            raise SafeError("未解析文件含同名候选，不能证明唯一定位。")
        return items
