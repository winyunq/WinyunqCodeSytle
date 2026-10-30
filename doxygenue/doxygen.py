"""Doxygen is the mandatory symbol authority, not an optional lexical fallback.

Normal indexing generates XML only. Publishing HTML is an explicit separate
operation. Local source bytes are only used to verify or project a Doxygen hit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from .cpp import EXCLUDED, EXTENSIONS, SafeError, Source, canonical, inside, sha, clean_comment

DEFAULT_ALIASES = {
    "伤害": ["damage", "hurt", "扣血"],
    "治疗": ["heal", "restorehealth", "恢复生命"],
    "生命值": ["health", "hitpoints"],
    "移动": ["move", "movement", "移动位置"],
    "生成": ["spawn", "create"],
    "销毁": ["destroy", "remove"],
}
MACROS = ["UCLASS(...)=", "USTRUCT(...)=", "UENUM(...)=", "UINTERFACE(...)=",
          "UFUNCTION(...)=", "UPROPERTY(...)=", "UMETA(...)=", "UPARAM(...)=",
          "GENERATED_BODY()=", "GENERATED_UCLASS_BODY()=", "GENERATED_USTRUCT_BODY()=",
          "FORCEINLINE=inline", "FORCEINLINE_DEBUGGABLE=inline"]

def native_filesystem_path(path: Path) -> Path:
    value = os.path.abspath(os.fspath(path))
    if os.name != "nt" or len(value) < 248 or value.startswith("\\\\?\\"):
        return Path(value)
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


def dump_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".due-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def xml_text(node) -> str:
    if node is None:
        return ""
    # Keep prose compact without concatenating paragraph boundaries.
    blocks = ["".join(p.itertext()).strip() for p in node.findall("para")]
    return "\n".join(blocks) if blocks else "".join(node.itertext()).strip()


def quote(value: str) -> str:
    if any(x in value for x in ('\n', '\r', '\x00', '"', '$')):
        raise SafeError("Doxygen 路径/预定义包含不支持的控制字符、引号或环境展开符。")
    return '"' + value.replace('\\', '/') + '"'


@dataclass
class Symbol:
    id: str
    refid: str
    name: str
    kind: str
    signature: str
    args: str
    file: str
    line: int
    bodyfile: str
    bodystart: int
    bodyend: int
    protection: str
    brief: str
    details: str
    inbody: str
    comments: str = ""
    documentation: dict = field(default_factory=dict)

    def summary(self, root: str) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "signature": self.signature[:240], "file": os.path.relpath(self.file, root),
                "line": self.line, "brief": self.brief[:160]}


class Catalog:
    def __init__(self, root: str, cache: Path, executable: str = ""):
        self.root = canonical(root)
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.settings_file = Path(self.root) / ".doxygenue" / "settings.json"
        self.docs_dir = Path(self.root) / "Documentation" / "DoxygenUE"
        self.executable = executable or os.environ.get("DOXYGEN_EXECUTABLE", "") or shutil.which("doxygen") or ""
        self.symbols: list[Symbol] = []
        self.fingerprint = ""
        self.hashes: dict[str, str] = {}
        self.version = ""
        self.last_build = {}
        self.compounds = []
        self._in_request = 0
        self._checked_request = False
        self.load_settings()

    def load_settings(self):
        self.settings = {"aliases": DEFAULT_ALIASES, "exclude": [], "defines": []}
        if self.settings_file.exists():
            try:
                data = json.loads(self.settings_file.read_text(encoding="utf-8-sig"))
                self.validate_settings(data)
                self.settings.update(data)
            except (ValueError, OSError) as exc:
                raise SafeError(f"配置读取失败，未忽略损坏配置：{exc}") from exc

    @staticmethod
    def validate_settings(data):
        if not isinstance(data, dict) or set(data) - {"aliases", "exclude", "defines"}:
            raise SafeError("配置只允许 aliases、exclude、defines；不能注入 Doxyfile/过滤器/可执行文件。")
        for key in ("exclude", "defines"):
            if key in data and (not isinstance(data[key], list) or len(data[key]) > 200 or any(not isinstance(s, str) or len(s) > 160 for s in data[key])):
                raise SafeError(f"{key} 必须是有界字符串列表。")
        if any(not re.fullmatch(r"[\w.-]+", s) for s in data.get("exclude", [])):
            raise SafeError("exclude 只接受目录名，不接受任意路径或 Doxyfile 内容。")
        if any(not re.fullmatch(r"[A-Za-z_]\w*(?:=[A-Za-z0-9_]+)?", s) for s in data.get("defines", [])):
            raise SafeError("defines 只接受 NAME 或 NAME=VALUE。")
        aliases = data.get("aliases", {})
        if not isinstance(aliases, dict) or len(aliases) > 200:
            raise SafeError("aliases 必须是小型显式同义词字典。")
        for k, values in aliases.items():
            if not isinstance(k, str) or not 1 <= len(k) <= 80 or not isinstance(values, list) or len(values) > 20 or any(not isinstance(x, str) or not 1 <= len(x) <= 80 for x in values):
                raise SafeError("aliases 项无效。")

    def check_binary(self) -> str:
        if not self.executable:
            raise SafeError("没有 Doxygen。运行 Bootstrap-Windows.cmd 或用 --doxygen 指定真实程序；本工具不会使用模拟索引或词法降级。")
        try:
            p = subprocess.run([self.executable, "--version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise SafeError(f"Doxygen 启动失败：{exc}") from exc
        version = p.stdout.strip()
        if p.returncode or not re.match(r"\d+\.\d+\.\d+", version):
            raise SafeError("Doxygen --version 未返回有效版本。")
        self.version = version
        return version

    def scan(self) -> list[Path]:
        excluded = {x.casefold() for x in EXCLUDED | set(self.settings["exclude"])}
        # Documentation is scanned separately: never feed arbitrary project Doxyfiles or scripts.
        excluded |= {"documentation"}
        files = []
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d.casefold() not in excluded and not Path(directory, d).is_symlink() and not inside(Path(directory,d),self.cache))
            for name in sorted(names):
                p = Path(directory, name)
                if p.suffix.lower() not in EXTENSIONS or name.endswith((".generated.h", ".gen.cpp")):
                    continue
                if p.is_symlink() or not inside(p, self.root):
                    continue
                if p.stat().st_size > 2 * 1024 * 1024:
                    raise SafeError(f"源码超过 2 MiB 安全上限：{p.relative_to(self.root)}。请缩小项目边界。")
                files.append(p)
                if len(files) > 20000:
                    raise SafeError("超过 20000 个源码文件；请选择模块或配置排除目录，不会返回不完整索引。")
        relative_keys = [p.relative_to(self.root).as_posix().casefold() for p in files]
        if len(relative_keys) != len(set(relative_keys)):
            raise SafeError("发现仅大小写不同的源码路径，无法建立跨Windows一致身份。")
        if self.docs_dir.exists():
            if self.docs_dir.is_symlink() or not inside(self.docs_dir, self.root):
                raise SafeError("文档目录不能位于项目边界之外。")
            files += sorted(p for p in self.docs_dir.glob("*.dox") if p.is_file() and not p.is_symlink())
        return files

    def stamp(self, files):
        parts = [(canonical(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files]
        return sha(json.dumps([parts, self.settings, self.executable, "schema-0.3"], sort_keys=True).encode())

    @contextmanager
    def request(self):
        if not self._in_request:
            self._checked_request = False
        self._in_request += 1
        try:
            yield
        finally:
            self._in_request -= 1
            if not self._in_request:
                self._checked_request = False

    def ensure(self, force=False):
        if self._in_request and self._checked_request and self.fingerprint and not force:
            return
        self._ensure(force)
        if self._in_request:
            self._checked_request = True

    def _ensure(self, force=False):
        self.load_settings()
        files = self.scan()
        stamp = self.stamp(files)
        if not force and stamp == self.fingerprint:
            return
        saved = self.cache / "index.json"
        if not force and saved.exists():
            try:
                data = json.loads(saved.read_text(encoding="utf-8"))
                if data["fingerprint"] == stamp and data["root"] == self.root:
                    self.symbols = [Symbol(**s) for s in data["symbols"]]
                    self.compounds = data.get("compounds", [])
                    self.fingerprint, self.hashes = stamp, data["hashes"]
                    self.version, self.last_build = data["version"], data["build"]
                    return
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self.build(files, stamp, html=False)

    def config(self, files, output, html=False):
        api_macros = set()
        for p in files:
            if p.suffix.lower() in EXTENSIONS:
                api_macros.update(re.findall(r"\b[A-Z][A-Z0-9_]*_API\b", p.read_text(encoding="utf-8-sig")))
        predefined = MACROS + [m + "=" for m in sorted(api_macros)] + self.settings["defines"]
        lines = [
            'PROJECT_NAME = "DoxygenUnrealEngine"', 'INPUT_ENCODING = UTF-8',
            "OUTPUT_DIRECTORY = " + quote(str(output)), "RECURSIVE = NO",
            "FILE_PATTERNS = *.h *.hpp *.hh *.hxx *.cpp *.cc *.cxx *.c *.inl *.dox",
            "EXTRACT_ALL = YES", "EXTRACT_PRIVATE = YES", "EXTRACT_STATIC = YES", "EXTRACT_ANON_NSPACES = YES",
            "ENABLE_PREPROCESSING = YES", "MACRO_EXPANSION = YES", "EXPAND_ONLY_PREDEF = YES",
            "SEARCH_INCLUDES = NO", "EXCLUDE_SYMLINKS = YES", "FULL_PATH_NAMES = YES",
            "GENERATE_XML = YES", "XML_PROGRAMLISTING = NO", "SOURCE_BROWSER = NO",
            "GENERATE_HTML = " + ("YES" if html else "NO"), "GENERATE_LATEX = NO",
            "HAVE_DOT = NO", "QUIET = YES", "WARNINGS = YES", "WARN_IF_UNDOCUMENTED = NO",
            "JAVADOC_AUTOBRIEF = YES", "HIDE_IN_BODY_DOCS = NO",
            "PREDEFINED = " + " ".join(quote(m) for m in predefined),
            "INPUT = " + " ".join(quote(str(p)) for p in files),
        ]
        return "\n".join(lines) + "\n"

    def build(self, files=None, stamp=None, html=False):
        self.check_binary()
        files = self.scan() if files is None else files
        if not files:
            raise SafeError("项目内没有可供 Doxygen 索引的 C/C++ 文件。")
        stamp = stamp or self.stamp(files)
        hashes = {canonical(p): sha(p.read_bytes()) for p in files}
        folder = Path(tempfile.mkdtemp(prefix="build-", dir=self.cache))
        config = self.config(files, folder, html)
        (folder / "Doxyfile").write_text(config, encoding="utf-8")
        start = time.perf_counter()
        try:
            p = subprocess.run([self.executable, str(folder / "Doxyfile")], cwd=self.root,
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=180, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise SafeError(f"Doxygen 索引失败，未退回整文件：{exc}") from exc
        (folder / "process.log").write_text(p.stdout + "\n" + p.stderr, encoding="utf-8")
        if p.returncode or not (folder / "xml" / "index.xml").is_file():
            raise SafeError(f"Doxygen 失败（{p.returncode}）；日志：{folder / 'process.log'}")
        if self.stamp(self.scan()) != stamp or any(sha(Path(k).read_bytes()) != v for k, v in hashes.items()):
            raise SafeError("源码/文档在 Doxygen 运行期间变化，丢弃本次索引并重试。")
        symbols = self.parse_xml(folder / "xml", set(hashes))
        build = {"engine": "Doxygen", "version": self.version, "elapsed_ms": round((time.perf_counter()-start)*1000, 3),
                 "symbol_count": len(symbols), "files": len(files), "xml": str(folder / "xml"),
                 "log": str(folder / "process.log"), "warning_count": p.stderr.lower().count("warning:"),
                 "html": str(folder / "html" / "index.html") if html else None}
        self.symbols, self.hashes, self.fingerprint, self.last_build = symbols, hashes, stamp, build
        dump_atomic(self.cache / "index.json", {"root": self.root, "fingerprint": stamp,
                    "hashes": hashes, "version": self.version, "build": build,
                    "symbols": [asdict(s) for s in symbols], "compounds": self.compounds})
        if html:
            dump_atomic(self.cache / "published.json", {"build": build, "fingerprint": stamp})
        # Keep XML/log evidence of recent builds, never unbounded whole-project history.
        folders = sorted(self.cache.glob("build-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        published = ""
        try:
            published = json.loads((self.cache/"published.json").read_text())["build"]["html"]
        except (OSError, ValueError, KeyError):
            pass
        for old in folders[3:]:
            if not published.startswith(str(old) + os.sep):
                shutil.rmtree(native_filesystem_path(old), ignore_errors=True)
        return build

    def parse_xml(self, folder: Path, allowed: set[str]) -> list[Symbol]:
        index = ET.parse(native_filesystem_path(folder / "index.xml")).getroot()
        if index.tag != "doxygenindex":
            raise SafeError("不是 Doxygen XML 索引。")
        found = {}
        self.compounds = []
        from .views import documentation_from_xml
        def location(value):
            if not value:
                return ""
            path = canonical(value if Path(value).is_absolute() else Path(self.root) / value)
            if path not in allowed or not inside(path, self.root):
                return ""
            return path
        for entry in index.findall("compound"):
            refid = entry.get("refid", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", refid):
                raise SafeError("XML compound refid 越界。")
            file = native_filesystem_path(folder / (refid + ".xml"))
            if file.stat().st_size > 32 * 1024 * 1024:
                raise SafeError("XML compound 超过安全上限。")
            tree = ET.parse(file).getroot()
            for compound in tree.findall("compounddef"):
                loc = compound.find("location")
                if loc is not None and compound.get("kind") in {"class", "struct", "namespace"}:
                    cp = location(loc.get("file"))
                    if cp:
                        self.compounds.append({"name": compound.findtext("compoundname") or "", "kind": compound.get("kind"), "file": cp, "line": int(loc.get("line", "0"))})
            for member in tree.findall(".//memberdef"):
                kind = member.get("kind")
                if kind not in {"function", "variable", "typedef", "enum", "property"}:
                    continue
                loc = member.find("location")
                if loc is None:
                    continue
                path, body = location(loc.get("file")), location(loc.get("bodyfile"))
                if not path or Path(path).suffix.lower() not in EXTENSIONS:
                    continue
                name = member.findtext("qualifiedname") or member.findtext("name") or ""
                name = re.sub(r"anonymous_namespace\{[^}]+\}::", "<anonymous>::", name)
                args = member.findtext("argsstring") or ""
                definition = member.findtext("definition") or name
                signature = (definition + args).rstrip(";") + ";"
                uid = sha((Path(path).relative_to(self.root).as_posix().casefold() + "\0" + name + "\0" + args + "\0" + kind).encode())[:20]
                symbol = Symbol(uid, member.get("id", ""), name, kind, signature, args, path,
                                int(loc.get("line", "0")), body, int(loc.get("bodystart", "0")),
                                int(loc.get("bodyend", "0")), member.get("prot", "public"),
                                xml_text(member.find("briefdescription")), xml_text(member.find("detaileddescription")),
                                xml_text(member.find("inbodydescription")))
                symbol.documentation = documentation_from_xml(member)
                if uid not in found or symbol.bodyend > found[uid].bodyend:
                    found[uid] = symbol
        # Ordinary // comments are not all emitted as Doxygen documentation.
        # Add only comments belonging to an already Doxygen-discovered member.
        source_cache = {}
        for symbol in found.values():
            texts = []
            for path in set(filter(None, [symbol.file, symbol.bodyfile])):
                if path not in source_cache:
                    try:
                        source_cache[path] = Source.load(path)
                    except (OSError, ValueError, UnicodeError):
                        source_cache[path] = None
                source = source_cache[path]
                if source is not None:
                    for o in source.occurrences:
                        if o.name == symbol.name:
                            texts += [clean_comment(c.value) for c in source.leading(o)]
                            texts += [clean_comment(c.value) for c in source.comments if o.start <= c.start < o.end]
            symbol.comments = "\n".join(texts)[:16000]
        return sorted(found.values(), key=lambda s: (s.name, s.args, s.file))

    def by_id(self, target_id: str) -> Symbol:
        self.ensure()
        result = [s for s in self.symbols if s.id == target_id]
        if len(result) != 1:
            raise SafeError("Target 已失效或不唯一；请重新搜索。")
        return result[0]


class RangeIndex:
    """Offset guard bound to the source files and lines found by Doxygen."""
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.sources, self.stamps, self.groups = {}, {}, {}
        self.bound_id = None

    def refresh(self):
        self.catalog.ensure()

    def resolve(self, name):
        self.refresh()
        symbols = [s for s in self.catalog.symbols if s.name == name]
        if self.bound_id:
            bound = [s for s in symbols if s.id == self.bound_id]
            if len(bound) != 1:
                raise SafeError("本次操作的源码定位已失效。")
            files = set(filter(None, (bound[0].file, bound[0].bodyfile)))
            # File qualification may distinguish homonyms in separate files,
            # but does not silently resolve an overload in the same file.
            symbols = [s for s in symbols if files.intersection(filter(None, (s.file, s.bodyfile)))]
        if len(symbols) != 1:
            raise SafeError("Doxygen 中存在同名重载/重复符号；接口可读，当前安全编辑器拒绝猜测源码范围。")
        symbol = symbols[0]
        if symbol.kind not in {"function", "variable"}:
            raise SafeError("此符号当前只支持 Doxygen 接口读取。")
        files = set(filter(None, [symbol.file, symbol.bodyfile]))
        items = []
        for path in sorted(files):
            raw = Path(path).read_bytes()
            if sha(raw) != self.catalog.hashes.get(path):
                self.catalog.fingerprint = ""
                self.catalog.ensure(force=True)
                raise SafeError("源文件相对 Doxygen 索引发生变化；索引已重建，请重试。")
            previous = self.sources.get(path)
            source = previous if previous and previous.raw == raw else Source.load(path, raw)
            self.sources[path] = source
            physical = [o for o in source.occurrences if o.name == name]
            if len([o for o in physical if o.role == "definition"]) > 1 or len([o for o in physical if o.role == "declaration"]) > 1:
                raise SafeError("同一物理文件有重复/条件分支同名对象；拒绝猜测。")
            for o in source.occurrences:
                if o.name != name:
                    continue
                first = source.text.count("\n", 0, o.start) + 1
                last = source.text.count("\n", 0, o.end - 1) + 1
                declaration_match = path == symbol.file and first <= symbol.line <= last
                definition_match = (o.role == "definition" and path == symbol.bodyfile and
                                    first <= symbol.bodystart <= last and last == symbol.bodyend)
                if declaration_match or definition_match:
                    items.append(o)
        if not items or any(sum(o.role == r for o in items) > 1 for r in ("declaration", "definition")):
            raise SafeError("Doxygen 位置无法唯一映射到原文件；不会退回整文件。")
        if symbol.kind == "function" and symbol.bodyend > 0 and not any(o.role == "definition" for o in items):
            raise SafeError("Doxygen 函数体范围与原始源码复核不一致。")
        self.groups[name] = items
        return items
