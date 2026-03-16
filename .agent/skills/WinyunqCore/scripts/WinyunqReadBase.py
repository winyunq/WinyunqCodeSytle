import os
import sys
import json
import re

try:
    from WinyunqBase import WinyunqBase, WinyunqAction
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqBase, WinyunqAction

class WinyunqReadBase(WinyunqBase):
    """
    Read 支柱基类 (WinyunqReadBase)
    支持穿透性检索 (Penetrative Search) 与 ReadForEdit 协议。
    """

    def get_category(self, file_path, name):
        if not name: return "Container"
        # 简单正则增强，区分类与函数
        content = ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
        except: return "Data"
        
        leaf_name = name.split("::")[-1]
        if re.search(fr"(class|struct|namespace)\s+{leaf_name}", content): return "Container"
        if re.search(fr"\b{leaf_name}\b\s*\(", content): return "Executable"
        return "Data"

    def execute_list(self, name=None):
        file_path = self.resolve_file_by_name(name) if name else self.state.get("work_path")
        if not file_path or not os.path.exists(file_path): return "[]"
        
        # TODO: 集成更深层的 Scope 穿透逻辑
        if os.path.isdir(file_path):
            return json.dumps(os.listdir(file_path), ensure_ascii=False)
            
        category = self.get_category(file_path, name)
        # 模拟返回，实际应由各语言 sub-skill 覆写逻辑
        return json.dumps(["Found1", "Found2"], ensure_ascii=False)

    def execute_read_for_edit(self, name):
        """
        [MAINTENANCE PROTOCOL] 读取代码配合编辑，强制保留所有注释。
        """
        file_path = self.resolve_file_by_name(name)
        if not file_path: return f"Error: Object '{name}' not found."
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 返回带注释的完整块或文件
        return content

    def execute_declaration(self, name):
        file_path = self.resolve_file_by_name(name)
        if not file_path: return "{}"
        return json.dumps({"name": name, "file": file_path, "type": "interface_placeholder"}, indent=2)

    def execute_reference(self, name):
        if not name: return "[]"
        # TODO: 调用 ripgrep 检索引用
        return "[]"
