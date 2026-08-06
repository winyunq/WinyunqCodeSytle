import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree


class WinyunqCodeSlicer:
    """Resolve one C++ function and project only the requested source facet."""

    SOURCE_EXTENSIONS = (".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx", ".inl")
    HEADER_EXTENSIONS = (".h", ".hpp", ".hh")
    IMPLEMENTATION_EXTENSIONS = (".cpp", ".cc", ".cxx", ".inl")
    EXCLUDED_DIRECTORIES = {
        ".git", ".vs", "Binaries", "DerivedDataCache", "Intermediate", "Saved"
    }

    def __init__(self):
        self._member_cache = {}
        self._candidate_cache = {}

    def read(self, name, work_path, filters=None, view="implementation", comment_part="all"):
        if not name or "::" not in name:
            return None

        member = self._resolve_member(name, work_path, filters or [])
        if not member:
            return None

        if view == "declaration":
            return self._read_declaration(member)
        if view == "implementation":
            return self._read_implementation(member, include_comments=False)
        if view == "body":
            return self._read_body(member)
        if view == "exact":
            return self._read_implementation(member, include_comments=True)
        if view == "comments":
            return self._read_comments(member, comment_part)
        return None

    def resolve(self, name, work_path, filters=None):
        """Return a copy of the physical mapping for one logical Target."""
        if not name or "::" not in name:
            return None
        member = self._resolve_member(name, work_path, filters or [])
        return dict(member) if member else None

    def _resolve_member(self, name, work_path, filters):
        work_path = os.path.abspath(work_path)
        candidate_files = self._find_candidate_files(name, work_path, filters)
        if not candidate_files:
            return None

        cache_key = self._cache_key(name, work_path, candidate_files)
        if cache_key in self._member_cache:
            return self._member_cache[cache_key]

        member = self._run_doxygen(name, candidate_files)
        if not member:
            member = self._resolve_lexically(name, candidate_files)
        if member:
            if len(self._member_cache) >= 128:
                self._member_cache.pop(next(iter(self._member_cache)))
            self._member_cache[cache_key] = member
        return member

    def _resolve_lexically(self, name, files):
        owner, leaf = name.rsplit("::", 1)
        owner_leaf = owner.split("::")[-1]
        declaration = None
        definition = None

        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as stream:
                    source = stream.read()
            except OSError:
                continue

            extension = os.path.splitext(path)[1].lower()
            if extension in self.HEADER_EXTENSIONS and declaration is None:
                declaration_match = re.search(rf"\b{re.escape(leaf)}\s*\(", source)
                if declaration_match:
                    declaration = (path, source.count("\n", 0, declaration_match.start()) + 1)
                else:
                    variable_match = re.search(rf"\b{re.escape(leaf)}\b[^;{{}}]*;", source)
                    if variable_match:
                        declaration = (path, source.count("\n", 0, variable_match.start()) + 1)

            if extension in self.IMPLEMENTATION_EXTENSIONS and definition is None:
                function_match = re.search(
                    rf"\b{re.escape(owner_leaf)}\s*::\s*{re.escape(leaf)}\s*\(",
                    source,
                )
                if function_match:
                    opening_brace = self._find_function_opening_brace(source, function_match.end())
                    if opening_brace is not None:
                        closing_brace = self._find_matching_brace(source, opening_brace)
                        if closing_brace is not None:
                            signature_start = source.rfind("\n", 0, function_match.start()) + 1
                            definition = (
                                path,
                                source.count("\n", 0, signature_start) + 1,
                                source.count("\n", 0, closing_brace) + 1,
                            )

        if not declaration and not definition:
            return None
        return {
            "kind": "function" if definition else "variable",
            "name": name,
            "args": "",
            "declaration_file": declaration[0] if declaration else None,
            "declaration_line": declaration[1] if declaration else 0,
            "definition_file": definition[0] if definition else None,
            "definition_start": definition[1] if definition else 0,
            "definition_end": definition[2] if definition else 0,
        }

    @staticmethod
    def _find_function_opening_brace(source, start):
        parenthesis_depth = 1
        index = start
        while index < len(source):
            character = source[index]
            if character == "(":
                parenthesis_depth += 1
            elif character == ")":
                parenthesis_depth -= 1
            elif character == "{" and parenthesis_depth == 0:
                return index
            elif character == ";" and parenthesis_depth == 0:
                return None
            index += 1
        return None

    @staticmethod
    def _find_matching_brace(source, opening_brace):
        depth = 0
        index = opening_brace
        state = "normal"
        quote = ""
        while index < len(source):
            character = source[index]
            following = source[index + 1] if index + 1 < len(source) else ""
            if state == "line_comment":
                if character == "\n":
                    state = "normal"
            elif state == "block_comment":
                if character == "*" and following == "/":
                    state = "normal"
                    index += 1
            elif state == "string":
                if character == "\\":
                    index += 1
                elif character == quote:
                    state = "normal"
            else:
                if character == "/" and following == "/":
                    state = "line_comment"
                    index += 1
                elif character == "/" and following == "*":
                    state = "block_comment"
                    index += 1
                elif character in {'"', "'"}:
                    state = "string"
                    quote = character
                elif character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    if depth == 0:
                        return index
            index += 1
        return None

    def _find_candidate_files(self, name, work_path, filters):
        owner = name.rsplit("::", 1)[0].split("::")[-1]
        candidate_key = (owner, os.path.abspath(work_path), tuple(sorted(filters)))
        cached = self._candidate_cache.get(candidate_key)
        if cached and all(os.path.isfile(path) for path in cached):
            return cached

        files = []
        ripgrep = shutil.which("rg")
        if ripgrep:
            command = [
                ripgrep,
                "--files-with-matches",
                "--fixed-strings",
                owner,
                work_path,
            ]
            for extension in self.SOURCE_EXTENSIONS:
                command.extend(["-g", f"*{extension}"])
            for directory in sorted(self.EXCLUDED_DIRECTORIES.union(filters)):
                command.extend(["-g", f"!**/{directory}/**"])
            try:
                process = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                    check=False,
                )
                files = [line.strip() for line in process.stdout.splitlines() if line.strip()]
            except (OSError, subprocess.SubprocessError):
                files = []

        if not files:
            excluded = self.EXCLUDED_DIRECTORIES.union(filters)
            for root, directories, names in os.walk(work_path):
                directories[:] = [directory for directory in directories if directory not in excluded]
                for file_name in names:
                    if not file_name.lower().endswith(self.SOURCE_EXTENSIONS):
                        continue
                    path = os.path.join(root, file_name)
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as stream:
                            if owner in stream.read():
                                files.append(path)
                    except OSError:
                        continue

        def score(path):
            extension = os.path.splitext(path)[1].lower()
            file_stem = os.path.splitext(os.path.basename(path))[0].lower()
            owner_key = self._normalize_ue_name(owner).lower()
            stem_key = self._normalize_ue_name(file_stem).lower()
            value = 0
            if extension in self.HEADER_EXTENSIONS:
                value += 30
            if extension in self.IMPLEMENTATION_EXTENSIONS:
                value += 20
            if owner_key in stem_key or stem_key in owner_key:
                value += 50
            if "generated" in file_stem:
                value -= 100
            return value

        unique_files = list(dict.fromkeys(os.path.abspath(path) for path in files if os.path.isfile(path)))
        unique_files.sort(key=score, reverse=True)
        result = unique_files[:12]
        if result:
            if len(self._candidate_cache) >= 128:
                self._candidate_cache.pop(next(iter(self._candidate_cache)))
            self._candidate_cache[candidate_key] = result
        return result

    @staticmethod
    def _normalize_ue_name(name):
        name = name.removeprefix("Gemini_")
        if len(name) > 1 and name[0] in "UAFISTE" and name[1].isupper():
            return name[1:]
        return name

    @staticmethod
    def _cache_key(name, work_path, files):
        revisions = []
        for path in files:
            try:
                stat = os.stat(path)
                revisions.append((path, stat.st_mtime_ns, stat.st_size))
            except OSError:
                revisions.append((path, 0, 0))
        return name, work_path, tuple(revisions)

    def _run_doxygen(self, name, files):
        doxygen = shutil.which("doxygen")
        if not doxygen:
            return None

        with tempfile.TemporaryDirectory(prefix="WinyunqCodeSlice-") as output_directory:
            inputs = " ".join(f'"{path.replace(os.sep, "/")}"' for path in files)
            output_path = output_directory.replace(os.sep, "/")
            configuration = f"""
PROJECT_NAME = WinyunqCodeSlice
OUTPUT_DIRECTORY = "{output_path}"
INPUT = {inputs}
FILE_PATTERNS = *.h *.hpp *.hh *.cpp *.cc *.cxx *.inl
RECURSIVE = NO
EXTRACT_ALL = YES
EXTRACT_PRIVATE = YES
EXTRACT_STATIC = YES
HIDE_IN_BODY_DOCS = NO
ENABLE_PREPROCESSING = YES
MACRO_EXPANSION = NO
SKIP_FUNCTION_MACROS = YES
GENERATE_HTML = NO
GENERATE_LATEX = NO
GENERATE_XML = YES
XML_OUTPUT = xml
XML_PROGRAMLISTING = NO
SOURCE_BROWSER = NO
REFERENCES_RELATION = NO
REFERENCED_BY_RELATION = NO
QUIET = YES
WARNINGS = NO
"""
            try:
                process = subprocess.run(
                    [doxygen, "-"],
                    input=configuration,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return None
            if process.returncode != 0:
                return None

            xml_directory = os.path.join(output_directory, "xml")
            matches = []
            for xml_name in os.listdir(xml_directory) if os.path.isdir(xml_directory) else []:
                if not xml_name.endswith(".xml") or xml_name in {"index.xml", "Doxyfile.xml"}:
                    continue
                xml_path = os.path.join(xml_directory, xml_name)
                try:
                    root = ElementTree.parse(xml_path).getroot()
                except (ElementTree.ParseError, OSError):
                    continue
                for element in root.findall(".//memberdef"):
                    kind = element.get("kind", "")
                    if kind not in {"function", "variable", "property"}:
                        continue
                    qualified_name = element.findtext("qualifiedname") or ""
                    definition = element.findtext("definition") or ""
                    if qualified_name == name or definition.endswith(name):
                        location = element.find("location")
                        if location is None:
                            continue
                        matches.append({
                            "kind": kind,
                            "name": qualified_name or name,
                            "args": element.findtext("argsstring") or "",
                            "declaration_file": location.get("file"),
                            "declaration_line": self._integer(location.get("line")),
                            "definition_file": location.get("bodyfile"),
                            "definition_start": self._integer(location.get("bodystart")),
                            "definition_end": self._integer(location.get("bodyend")),
                        })
            if not matches:
                return None
            matches.sort(key=lambda item: bool(item.get("definition_file")), reverse=True)
            return matches[0]

    @staticmethod
    def _integer(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _read_declaration(self, member):
        path = member.get("declaration_file")
        line_number = member.get("declaration_line", 0)
        if not path or line_number <= 0:
            return None
        lines = self._read_lines(path)
        if not lines:
            return None

        start, end = self._declaration_range(lines, line_number - 1)
        documentation = self._clean_comment(self._leading_comment(lines, start))
        declaration = "".join(lines[start:end + 1]).strip()
        parts = []
        if documentation:
            parts.append(documentation)
        parts.append(declaration)
        return "\n".join(parts).strip()

    def _read_implementation(self, member, include_comments):
        path = member.get("definition_file")
        start = member.get("definition_start", 0)
        end = member.get("definition_end", 0)
        if not path or start <= 0 or end < start:
            declaration_file = member.get("declaration_file")
            declaration_line = member.get("declaration_line", 0)
            if not declaration_file or declaration_line <= 0:
                return None
            lines = self._read_lines(declaration_file)
            if not lines:
                return None
            declaration_start, declaration_end = self._declaration_range(
                lines, declaration_line - 1
            )
            declaration = "".join(lines[declaration_start:declaration_end + 1]).strip()
            if include_comments:
                documentation = self._leading_comment(lines, declaration_start)
                return "\n".join(part for part in [documentation.strip(), declaration] if part)
            code, _ = self._split_comments(declaration, declaration_line)
            return self._compact_blank_lines(code)
        lines = self._read_lines(path)
        if not lines:
            return None
        source = "".join(lines[start - 1:end]).strip()
        if include_comments:
            return source
        code, _ = self._split_comments(source, start)
        return self._compact_blank_lines(code)

    def _read_body(self, member):
        source = self._read_implementation(member, include_comments=True)
        if not source or member.get("kind") != "function":
            return None
        leaf = member.get("name", "").rsplit("::", 1)[-1]
        name_match = re.search(rf"\b{re.escape(leaf)}\s*\(", source)
        if not name_match:
            return None
        opening = self._find_function_opening_brace(source, name_match.end())
        if opening is None:
            return None
        closing = self._find_matching_brace(source, opening)
        if closing is None:
            return None
        body, _ = self._split_comments(source[opening + 1:closing], 1)
        return self._compact_blank_lines(body)

    def _read_comments(self, member, comment_part="all"):
        declaration_file = member.get("declaration_file")
        declaration_line = member.get("declaration_line", 0)
        definition_file = member.get("definition_file")
        definition_start = member.get("definition_start", 0)
        definition_end = member.get("definition_end", 0)

        declaration_comment = ""
        if declaration_file and declaration_line > 0:
            lines = self._read_lines(declaration_file)
            if lines:
                start, _ = self._declaration_range(lines, declaration_line - 1)
                declaration_comment = self._clean_comment(self._leading_comment(lines, start))

        definition_comment = ""
        body_comments = []
        if definition_file and definition_start > 0:
            lines = self._read_lines(definition_file)
            if lines:
                definition_comment = self._clean_comment(
                    self._leading_comment(lines, definition_start - 1)
                )
                source = "".join(lines[definition_start - 1:definition_end])
                _, body_comments = self._split_comments(source, definition_start)

        result = {
            "declaration": declaration_comment,
            "definition": "" if definition_comment == declaration_comment else definition_comment,
            "body": body_comments,
        }
        if comment_part in {"declaration", "definition"}:
            return result[comment_part]
        if comment_part == "body":
            return json.dumps(result["body"], ensure_ascii=False, separators=(",", ":"))
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _read_lines(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as stream:
                return stream.readlines()
        except OSError:
            return []

    @staticmethod
    def _declaration_range(lines, line_index):
        start = max(0, min(line_index, len(lines) - 1))
        cursor = start - 1
        while cursor >= 0:
            stripped = lines[cursor].strip()
            if re.match(r"^(UFUNCTION|UE_DEPRECATED|UE_NODISCARD|UE_REQUIRES)\b", stripped):
                start = cursor
                cursor -= 1
                continue
            break

        end = max(0, min(line_index, len(lines) - 1))
        limit = min(len(lines), end + 80)
        while end + 1 < limit and ";" not in "".join(lines[start:end + 1]):
            end += 1
        return start, end

    @staticmethod
    def _leading_comment(lines, code_start):
        cursor = code_start - 1
        while cursor >= 0 and not lines[cursor].strip():
            cursor -= 1
        if cursor < 0:
            return ""

        stripped = lines[cursor].strip()
        if stripped.endswith("*/"):
            end = cursor
            while cursor >= 0 and "/*" not in lines[cursor]:
                cursor -= 1
            if cursor >= 0:
                return "".join(lines[cursor:end + 1])
        if stripped.startswith("//"):
            end = cursor
            while cursor >= 0 and lines[cursor].lstrip().startswith("//"):
                cursor -= 1
            return "".join(lines[cursor + 1:end + 1])
        return ""

    @staticmethod
    def _clean_comment(comment):
        if not comment:
            return ""
        lines = []
        for line in comment.splitlines():
            cleaned = line.strip()
            cleaned = re.sub(r"^/\*+", "", cleaned)
            cleaned = re.sub(r"\*+/\s*$", "", cleaned)
            cleaned = re.sub(r"^///?\s?", "", cleaned)
            cleaned = re.sub(r"^\*\s?", "", cleaned)
            cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)

    def _split_comments(self, source, start_line):
        code = []
        comments = []
        index = 0
        line = start_line
        length = len(source)
        while index < length:
            current = source[index]
            following = source[index + 1] if index + 1 < length else ""

            if current == "R" and following == '"':
                delimiter_end = source.find("(", index + 2)
                if delimiter_end != -1:
                    delimiter = source[index + 2:delimiter_end]
                    raw_end = source.find(")" + delimiter + '"', delimiter_end + 1)
                    if raw_end != -1:
                        raw_end += len(delimiter) + 2
                        fragment = source[index:raw_end]
                        code.append(fragment)
                        line += fragment.count("\n")
                        index = raw_end
                        continue

            if current in {'"', "'"}:
                quote = current
                start = index
                index += 1
                escaped = False
                while index < length:
                    character = source[index]
                    if character == "\n":
                        line += 1
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == quote:
                        index += 1
                        break
                    index += 1
                code.append(source[start:index])
                continue

            if current == "/" and following == "/":
                comment_line = line
                end = source.find("\n", index + 2)
                if end == -1:
                    end = length
                raw = source[index:end]
                text = self._clean_comment(raw)
                if text:
                    comments.append({"line": comment_line, "kind": "line", "text": text})
                index = end
                continue

            if current == "/" and following == "*":
                comment_line = line
                end = source.find("*/", index + 2)
                end = length if end == -1 else end + 2
                raw = source[index:end]
                text = self._clean_comment(raw)
                if text:
                    comments.append({"line": comment_line, "kind": "block", "text": text})
                newline_count = raw.count("\n")
                code.append("\n" * newline_count)
                line += newline_count
                index = end
                continue

            code.append(current)
            if current == "\n":
                line += 1
            index += 1

        return "".join(code), comments

    @staticmethod
    def _compact_blank_lines(code):
        output = []
        for line in code.splitlines():
            stripped_right = line.rstrip()
            if not stripped_right:
                continue
            output.append(stripped_right)
        return "\n".join(output).strip()
