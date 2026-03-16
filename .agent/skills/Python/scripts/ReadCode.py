import os
import sys
import ast
import json

# --- 继承体系 ---
CORE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "WinyunqCore", "scripts"))
sys.path.append(CORE_PATH)
from WinyunqBase import WinyunqBase, WinyunqAction

class PythonSkill(WinyunqBase):
    """
    Python 专属技能 [TACTICAL OVERWRITE]
    继承 WinyunqBase，针对 Python 语法的 AST 解析进行覆写。
    """
    
    @WinyunqAction("ReadCode", "Definition", "使用 AST 精准读取 Python 定义")
    def read_code(self, name, action="Definition"):
        # Overwrite: 专门实现 Python 的解析逻辑
        target_file = self.get_full_target()
        if not target_file or not os.path.exists(target_file):
             return "File not set or missing."

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                    lines = content.splitlines()
                    start = node.lineno - 1
                    # Find end by indent...
                    end = start + 1
                    for i in range(start + 1, len(lines)):
                        if lines[i].strip() and (len(lines[i]) - len(lines[i].lstrip())) <= node.col_offset: break
                        end = i + 1
                    return "\n".join(lines[start:end])
        except: pass
        return f"Symbol {name} not found in {os.path.basename(target_file)}"

if __name__ == "__main__":
    # 模拟工具执行
    skill = PythonSkill()
    if len(sys.argv) > 2:
        if sys.argv[1] == "Definition":
            print(skill.read_code(sys.argv[2]))
