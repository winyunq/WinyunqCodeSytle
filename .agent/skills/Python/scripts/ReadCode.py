import os
import sys
import argparse
import ast
import re
from Common import Common

class ReferenceVisitor(ast.NodeVisitor):
    def __init__(self, target_name):
        self.target_name = target_name
        self.references = []
        self.current_scope = "Global"

    def visit_FunctionDef(self, node):
        prev_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = prev_scope

    def visit_ClassDef(self, node):
        prev_scope = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = prev_scope

    def visit_Name(self, node):
        if node.id == self.target_name:
            self._add_ref(node)
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        if node.attr == self.target_name:
            self._add_ref(node)
        self.generic_visit(node)

    def _add_ref(self, node):
        self.references.append({
            "scope": self.current_scope,
            "line": node.lineno
        })

class CodeReader:
    """
    代码读取器 [LOCKED]
    支持查询 Declaration (文档), Definition (实现), Reference (引用)。
    """
    
    def __init__(self, use_target=True):
        self.file_path, self.scope = Common.get_full_target() if use_target else (None, None)

    def _read_content(self):
        if not self.file_path or not os.path.exists(self.file_path): return ""
        with open(self.file_path, 'r', encoding='utf-8') as f: return f.read()

    def get_declaration(self, name):
        """
        查询代码声明 (主要返回注释/Docstring)
        """
        if not self.file_path: return
        content = self._read_content()
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                    doc = ast.get_docstring(node)
                    print(f"--- {name} 声明 (Docstring) ---")
                    print(doc if doc else "(无文档)")
                    return
            print(f"未找到对象: {name}")
        except Exception as e:
            print(f"解析错误: {e}")

    def get_definition(self, name, mode="code"):
        """
        查询代码定义
        
        Args:
            mode (str):
                - 'code': 仅代码 (剔除 # 注释和 Docstring)
                - 'full': 原始内容 (代码 + 注释)
                - 'comment': 仅注释 (Docstring + # 注释)
        """
        if not self.file_path: return
        content = self._read_content()
        lines = content.splitlines()
        
        target_node = None
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                    target_node = node
                    break
        except: return

        if not target_node: print(f"未找到对象: {name}"); return

        # 确定范围
        s = target_node.lineno - 1
        base = target_node.col_offset
        # 简单结束行推断 (同 WriteCode)
        e = s + 1
        for i in range(s+1, len(lines)):
            l = lines[i]
            if not l.strip(): continue
            if (len(l) - len(l.lstrip())) <= base: break
            e = i + 1
        
        block_lines = lines[s:e]
        
        if mode == "full":
            print(f"--- {name} 定义 (完整) ---")
            print("\n".join(block_lines))
            
        elif mode == "code":
            print(f"--- {name} 定义 (仅代码) ---")
            # 过滤 Docstring 和 # 注释
            # 1. 过滤 #
            filtered = [l for l in block_lines if not l.strip().startswith("#")]
            # 2. 过滤 Docstring (通过 AST 再解析一次 block? 比较重)
            # 简单正则过滤 """..."""? 风险较大。
            # 更好的方法：只过滤掉纯注释行。保留 docstring，因为它是声明的一部分？
            # 用户要求 "默认不返回注释"，通常包含 Docstring。
            # 让我们尝试简单过滤:
            # 如果某行 strip 后以 """ 或 r""" 开头，认为是 docstring 的一部分? 
            # 实际上 docstring 可能跨行。
            # 我们可以利用 ast.get_docstring 获取内容，然后在文本中 replace 为空?
            
            # 方法: 重新组合 text -> ast -> 移除 docstring node -> unparse (Python 3.9+ ast.unparse)
            # 如果环境支持 ast.unparse:
            try:
                # 提取该节点的源码 (需用 ast.get_source_segment 但这在 3.8+ 且需 support)
                # 简单备选: 输出 exclude # lines. Docstring is expression statement.
                clean_lines = []
                in_docstring = False
                for l in block_lines:
                    strip_l = l.strip()
                    if strip_l.startswith("#"): continue
                    
                    # 极简 Docstring 过滤 (针对 Winyunq 标准格式)
                    # 假设 Docstring 是独立的 block
                    if '"""' in l and l.count('"""') == 2: continue # 单行 docstring
                    if '"""' in l: 
                        in_docstring = not in_docstring # 切换状态
                        continue
                    if in_docstring: continue
                    
                    clean_lines.append(l)
                print("\n".join(clean_lines))
            except:
                print("处理失败，输出原始内容")
                print("\n".join(block_lines))

        elif mode == "comment":
            print(f"--- {name} 定义 (仅注释) ---")
            # 提取 Docstring
            doc = ast.get_docstring(target_node)
            if doc: 
                print("[Docstring]")
                print(doc)
            
            # 提取 # 注释
            print("\n[Implementation Comments]")
            for l in block_lines:
                if l.strip().startswith("#"):
                    print(l.strip())

    def get_references(self, name):
        """
        查询代码引用 (返回引用上下文)
        """
        if not self.file_path: return
        content = self._read_content()
        lines = content.splitlines()
        
        try:
            tree = ast.parse(content)
            visitor = ReferenceVisitor(name)
            visitor.visit(tree)
            
            if not visitor.references:
                print(f"未找到 '{name}' 的引用。")
                return
            
            print(f"--- '{name}' 的引用 ({len(visitor.references)} 处) ---")
            for ref in visitor.references:
                line_idx = ref['line'] - 1
                scope = ref['scope']
                # 获取行内容
                code_line = lines[line_idx].strip()
                # 尝试获取上一行注释
                comment = ""
                if line_idx > 0 and lines[line_idx-1].strip().startswith("#"):
                    comment = lines[line_idx-1].strip()
                
                print(f"Scope: {scope} | Line: {ref['line']}")
                if comment: print(f"  Comment: {comment}")
                print(f"  Code:    {code_line}")
                print("-" * 20)
                
        except Exception as e:
            print(f"分析错误: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    # Declaration
    p_decl = subparsers.add_parser("Declaration", help="查询声明(Doc)")
    p_decl.add_argument("name")
    
    # Definition
    p_def = subparsers.add_parser("Definition", help="查询定义(Impl)")
    p_def.add_argument("name")
    p_def.add_argument("--mode", choices=['code', 'full', 'comment'], default='code', help="code=仅代码, full=全部, comment=仅注释")

    # Reference
    p_ref = subparsers.add_parser("Reference", help="查询引用(Usage)")
    p_ref.add_argument("name")

    args = parser.parse_args()
    reader = CodeReader()
    
    if args.command == "Declaration": reader.get_declaration(args.name)
    elif args.command == "Definition": reader.get_definition(args.name, args.mode)
    elif args.command == "Reference": reader.get_references(args.name)
    else: parser.print_help()
