import difflib
import hashlib
import json
import os
import re
import tempfile
import textwrap

try:
    from WinyunqCodeSlicer import WinyunqCodeSlicer
except ImportError:
    from .WinyunqCodeSlicer import WinyunqCodeSlicer


class WinyunqTargetEditor:
    """Apply revision-checked, comment-preserving edits inside one function Target."""

    def __init__(self, slicer=None):
        self.slicer = slicer or WinyunqCodeSlicer()

    def prepare(self, target, work_path, filters=None):
        member = self.slicer.resolve(target, work_path, filters or [])
        location = self._function_location(member, work_path)
        if not location:
            raise ValueError(f"Function Target '{target}' could not be resolved.")

        source_bytes = self._read_bytes(location["file"])
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        implementation = self.slicer.read(
            target,
            work_path,
            filters or [],
            view="implementation",
        )
        ticket = {
            "id": hashlib.sha256(
                f"{target}\0{location['file']}\0{source_hash}".encode("utf-8")
            ).hexdigest()[:20],
            "target": target,
            "file": location["file"],
            "work_path": os.path.abspath(work_path),
            "filters": list(filters or []),
            "source_hash": source_hash,
        }
        return {
            "target": target,
            "ticket": ticket,
            "implementation": implementation or "",
        }

    def preview(self, ticket, old_code, new_code):
        plan = self._plan(ticket, old_code, new_code)
        return {
            "status": "preview",
            "target": ticket["target"],
            "file": ticket["file"],
            "replacement": {
                "before": plan["old_source"],
                "after": plan["replacement"],
            },
            "diff": plan["diff"],
        }

    def replace(self, ticket, old_code, new_code):
        plan = self._plan(ticket, old_code, new_code)
        self._atomic_write(plan["file"], plan["new_bytes"])

        new_hash = hashlib.sha256(plan["new_bytes"]).hexdigest()
        updated_ticket = dict(ticket)
        updated_ticket["source_hash"] = new_hash
        updated_ticket["id"] = hashlib.sha256(
            f"{ticket['target']}\0{ticket['file']}\0{new_hash}".encode("utf-8")
        ).hexdigest()[:20]
        return {
            "status": "applied",
            "target": ticket["target"],
            "file": ticket["file"],
            "ticket": updated_ticket,
            "preserved": {
                "signature": True,
                "comments": True,
                "sibling_targets": True,
            },
        }

    def _plan(self, ticket, old_code, new_code):
        self._validate_ticket(ticket)
        if not old_code or not old_code.strip():
            raise ValueError("old_code must identify existing code inside the Target body.")
        if not new_code or not new_code.strip():
            raise ValueError("Empty replacement is deletion; use an explicit delete operation.")
        if self._contains_comment(new_code):
            raise ValueError(
                "Code writes cannot contain comments. Update comments in a separate operation."
            )

        path = ticket["file"]
        source_bytes = self._read_bytes(path)
        current_hash = hashlib.sha256(source_bytes).hexdigest()
        if current_hash != ticket.get("source_hash"):
            raise ValueError("Source changed after Prepare; prepare the Target again.")

        text, bom = self._decode(source_bytes)
        member = self.slicer.resolve(
            ticket["target"], ticket["work_path"], ticket.get("filters", [])
        )
        location = self._function_location(member, ticket["work_path"], text)
        if not location or os.path.normcase(location["file"]) != os.path.normcase(path):
            raise ValueError("Target mapping changed after Prepare; prepare the Target again.")

        body_start = location["body_start"]
        body_end = location["body_end"]
        body = text[body_start:body_end]
        source_tokens, comment_ranges = self._tokenize(body)
        requested_tokens, _ = self._tokenize(old_code)
        if not requested_tokens:
            raise ValueError("old_code does not contain any C++ tokens.")

        matches = self._find_token_matches(source_tokens, requested_tokens)
        if not matches:
            raise ValueError("old_code was not found inside the current Target body.")
        if len(matches) > 1:
            raise ValueError("old_code is ambiguous inside the Target; provide a narrower snippet.")

        first, last = matches[0]
        local_start = source_tokens[first][1]
        local_end = source_tokens[last][2]
        if any(start < local_end and end > local_start for start, end in comment_ranges):
            raise ValueError(
                "The requested replacement crosses a protected comment; use a smaller code snippet."
            )

        replace_start = body_start + local_start
        replace_end = body_start + local_end
        old_source = text[replace_start:replace_end]
        replacement = self._indent_replacement(text, replace_start, new_code)
        new_text = text[:replace_start] + replacement + text[replace_end:]
        new_bytes = (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8")
        diff = "\n".join(
            difflib.unified_diff(
                old_source.splitlines(),
                replacement.splitlines(),
                fromfile="before",
                tofile="after",
                lineterm="",
            )
        )
        return {
            "file": path,
            "old_source": old_source,
            "replacement": replacement,
            "new_bytes": new_bytes,
            "diff": diff,
        }

    @staticmethod
    def _validate_ticket(ticket):
        required = {"target", "file", "work_path", "source_hash"}
        if not isinstance(ticket, dict) or not required.issubset(ticket):
            raise ValueError("No valid edit ticket is active; call Prepare first.")
        file_path = os.path.abspath(ticket["file"])
        work_path = os.path.abspath(ticket["work_path"])
        try:
            inside_boundary = os.path.commonpath([file_path, work_path]) == work_path
        except ValueError:
            inside_boundary = False
        if not inside_boundary:
            raise ValueError("The edit Target is outside the active work path.")

    def _function_location(self, member, work_path, existing_text=None):
        if not member or member.get("kind") != "function":
            return None
        path = member.get("definition_file")
        start_line = member.get("definition_start", 0)
        end_line = member.get("definition_end", 0)
        if not path or start_line <= 0 or end_line < start_line:
            return None
        path = os.path.abspath(path)
        boundary = os.path.abspath(work_path)
        try:
            if os.path.commonpath([path, boundary]) != boundary:
                return None
        except ValueError:
            return None

        text = existing_text
        if text is None:
            text, _ = self._decode(self._read_bytes(path))
        qualified_name = member.get("name", "")
        if "::" in qualified_name:
            owner, leaf = qualified_name.rsplit("::", 1)
            owner_leaf = owner.rsplit("::", 1)[-1]
            definitions = re.findall(
                rf"\b{re.escape(owner_leaf)}\s*::\s*{re.escape(leaf)}\s*\(",
                text,
            )
            if len(definitions) > 1:
                raise ValueError(
                    "The Target has overloaded definitions and is not uniquely addressable yet."
                )
        line_offsets = [0]
        for match in re.finditer("\n", text):
            line_offsets.append(match.end())
        if start_line > len(line_offsets):
            return None
        definition_start = line_offsets[start_line - 1]
        definition_limit = (
            line_offsets[end_line] if end_line < len(line_offsets) else len(text)
        )
        definition = text[definition_start:definition_limit]
        leaf = member.get("name", "").rsplit("::", 1)[-1]
        name_match = re.search(rf"\b{re.escape(leaf)}\s*\(", definition)
        if not name_match:
            return None
        opening = self.slicer._find_function_opening_brace(
            definition, name_match.end()
        )
        if opening is None:
            return None
        closing = self.slicer._find_matching_brace(definition, opening)
        if closing is None:
            return None
        return {
            "file": path,
            "body_start": definition_start + opening + 1,
            "body_end": definition_start + closing,
        }

    @staticmethod
    def _tokenize(source):
        tokens = []
        comments = []
        index = 0
        length = len(source)
        multi_operators = (
            "<=>", "<<=", ">>=", "->*", "...", "::", "->", "++", "--",
            "==", "!=", "<=", ">=", "&&", "||", "+=", "-=", "*=", "/=",
            "%=", "&=", "|=", "^=", "<<", ">>", ".*",
        )
        while index < length:
            character = source[index]
            following = source[index + 1] if index + 1 < length else ""
            if character.isspace():
                index += 1
                continue
            if character == "/" and following == "/":
                end = source.find("\n", index + 2)
                end = length if end == -1 else end
                comments.append((index, end))
                index = end
                continue
            if character == "/" and following == "*":
                end = source.find("*/", index + 2)
                end = length if end == -1 else end + 2
                comments.append((index, end))
                index = end
                continue
            if character == "R" and following == '"':
                delimiter_end = source.find("(", index + 2)
                if delimiter_end != -1:
                    delimiter = source[index + 2:delimiter_end]
                    raw_end = source.find(")" + delimiter + '"', delimiter_end + 1)
                    if raw_end != -1:
                        raw_end += len(delimiter) + 2
                        tokens.append((source[index:raw_end], index, raw_end))
                        index = raw_end
                        continue
            if character in {'"', "'"}:
                quote = character
                end = index + 1
                while end < length:
                    if source[end] == "\\":
                        end += 2
                        continue
                    if source[end] == quote:
                        end += 1
                        break
                    end += 1
                tokens.append((source[index:end], index, end))
                index = end
                continue
            identifier = re.match(r"[A-Za-z_]\w*", source[index:])
            if identifier:
                end = index + identifier.end()
                tokens.append((source[index:end], index, end))
                index = end
                continue
            number = re.match(
                r"(?:0[xX][0-9A-Fa-f']+|0[bB][01']+|(?:\d[\d']*)(?:\.\d*)?(?:[eE][+-]?\d+)?)[A-Za-z0-9_]*",
                source[index:],
            )
            if number:
                end = index + number.end()
                tokens.append((source[index:end], index, end))
                index = end
                continue
            operator = next(
                (item for item in multi_operators if source.startswith(item, index)), None
            )
            end = index + len(operator or character)
            tokens.append((source[index:end], index, end))
            index = end
        return tokens, comments

    @staticmethod
    def _find_token_matches(source_tokens, requested_tokens):
        source_values = [item[0] for item in source_tokens]
        requested_values = [item[0] for item in requested_tokens]
        width = len(requested_values)
        return [
            (index, index + width - 1)
            for index in range(0, len(source_values) - width + 1)
            if source_values[index:index + width] == requested_values
        ]

    @classmethod
    def _contains_comment(cls, source):
        _, comments = cls._tokenize(source)
        return bool(comments)

    @staticmethod
    def _indent_replacement(full_source, replace_start, replacement):
        normalized = textwrap.dedent(replacement).strip()
        newline = "\r\n" if "\r\n" in full_source else "\n"
        line_start = full_source.rfind("\n", 0, replace_start) + 1
        prefix = full_source[line_start:replace_start]
        indentation = prefix if not prefix.strip() else ""
        lines = normalized.splitlines()
        if len(lines) <= 1:
            return normalized
        return lines[0] + newline + newline.join(
            indentation + line for line in lines[1:]
        )

    @staticmethod
    def _read_bytes(path):
        with open(path, "rb") as stream:
            return stream.read()

    @staticmethod
    def _decode(source_bytes):
        bom = source_bytes.startswith(b"\xef\xbb\xbf")
        payload = source_bytes[3:] if bom else source_bytes
        return payload.decode("utf-8"), bom

    @staticmethod
    def _atomic_write(path, content):
        directory = os.path.dirname(path)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".winyunq-edit-", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
