import os
import sys
import json
import re

try:
    from WinyunqBase import WinyunqBase, WinyunqAction
    from WinyunqCodeSlicer import WinyunqCodeSlicer
    from WinyunqParser import WinyunqParser
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqBase, WinyunqAction
    from WinyunqCodeSlicer import WinyunqCodeSlicer
    from WinyunqParser import WinyunqParser

class WinyunqReadBase(WinyunqBase):
    """
    Read 支柱基类 (WinyunqReadBase)
    支持穿透性检索 (Penetrative Search) 与 ReadForEdit 协议。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = WinyunqParser()
        self.code_slicer = WinyunqCodeSlicer()

    def get_category(self, file_path, name):
        if not name: return "Container"
        # 简单正则增强，区分类与函数
        content = ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
        except: return "Data"

        leaf_name = name.split("::")[-1]
        if re.search(fr"(class|struct|namespace)\s+(?:\w+_)?{leaf_name}", content): return "Container"
        if re.search(fr"\b{leaf_name}\b\s*\(", content): return "Executable"
        return "Data"

    def execute_list(self, name=None):
        """
        [INDEX FIRST] 利用 Universal Resolver 定位并列出成员。
        """
        file_path = self.resolve_file_by_name(name) if name else self.state.get("work_path")

        if not file_path or not os.path.exists(file_path): return "[]"

        if os.path.isdir(file_path):
            return json.dumps(os.listdir(file_path), ensure_ascii=False)

        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()

        taxonomy = self.parser.get_taxonomy(code)
        results = []

        # 匹配逻辑：如果 name 是类名，列出其成员；如果是成员名，列出其全称
        leaf_name = name.split("::")[-1] if name else None

        for item in taxonomy:
            if item["name"] == leaf_name or name is None or (leaf_name and leaf_name[1:] == item["name"] and leaf_name[0].lower() in "auf"):
                for child in item["children"]:
                    results.append(child["name"])
                return json.dumps(results, ensure_ascii=False)

        for item in taxonomy:
            for child in item["children"]:
                if leaf_name and child["name"] == leaf_name:
                    results.append(child["full_name"])

        return json.dumps(results, ensure_ascii=False)

    def execute_declaration(self, name):
        """
        [INDEX FIRST] 返回带索引特征的声明信息。
        """
        compact = self._read_compact_target(name, "declaration")
        if compact is not None:
            return compact

        file_path = self.resolve_file_by_name(name)
        if not file_path: return "{}"

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            taxonomy = self.parser.get_taxonomy(code)
            leaf_name = name.split("::")[-1]

            final_results = []
            for item in taxonomy:
                if item["name"] == leaf_name or (leaf_name[1:] == item["name"] and leaf_name[0].lower() in "auf"):
                    final_results.append({
                        "type": "class",
                        "priority": 3,
                        "name": item["name"],
                        "doc": item["doc"],
                        "members_taxonomy": [{"name": c["name"], "type": c["type"], "brief": c["doc"].get("brief", "")} for c in item["children"]]
                    })
                for child in item["children"]:
                    if child["name"] == leaf_name:
                        p = 1 if child["type"] == "method" else 2
                        child["priority"] = p
                        final_results.append(child)

            if final_results:
                final_results.sort(key=lambda x: x.get("priority", 99))
                return json.dumps(final_results[0], indent=2, ensure_ascii=False)
        except: pass

        return "{}"

    def execute_reference(self, name):
        """检索对象在当前 Working Path 内的所有引用位置"""
        if not name: return "[]"

        results = []
        work_path = self.state.get("work_path", self.root)

        # 由于系统环境可能没有 rg，使用 grep_search (假设该工具注入在系统能力中)
        # 但我们作为基座，使用 os.walk 兼容性最好，或者尝试调用外部工具
        try:
            from run_command import run_command # 模拟，实际应直接在 python 中实现
        except: pass

        # 正则匹配 A::B 或 B (按需检索)
        pattern = re.compile(fr"\b{name}\b")

        for root, dirs, files in os.walk(work_path):
            # 过滤
            filters = self.state.get("filters", [])
            dirs[:] = [d for d in dirs if d not in filters]

            for f in files:
                if f.startswith(self.DEFAULT_GEMINI_PREFIX): continue
                if not (f.endswith(".h") or f.endswith(".hpp") or f.endswith(".cpp")): continue

                f_path = os.path.join(root, f)
                try:
                    with open(f_path, 'r', encoding='utf-8') as content_f:
                        for i, line in enumerate(content_f):
                            if pattern.search(line):
                                results.append({
                                    "file": os.path.relpath(f_path, work_path),
                                    "line": i + 1,
                                    "context": line.strip()
                                })
                except: continue

        return json.dumps(results, indent=2, ensure_ascii=False)

    def execute_definition(self, name):
        compact = self._read_compact_target(name, "implementation")
        if compact is not None:
            return compact
        return self.execute_read_for_edit(name)

    def execute_comments(self, name, part="body"):
        compact = self._read_compact_target(name, "comments", part)
        return compact if compact is not None else "{}"

    def execute_read_for_edit(self, name):
        """
        [MAINTENANCE PROTOCOL] 读取代码配合编辑，强制保留所有注释。
        """
        compact = self._read_compact_target(name, "exact")
        if compact is not None:
            return compact

        file_path = self.resolve_file_by_name(name)
        if not file_path: return f"Error: Object '{name}' not found."

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content

    def _read_compact_target(self, name, view, comment_part="all"):
        if not name or "::" not in name:
            return None
        work_path = self.state.get("work_path", self.root)
        filters = self.state.get("filters", [])
        return self.code_slicer.read(name, work_path, filters, view, comment_part)
