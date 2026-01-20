import os
import sys
import argparse
import ast
import re
from Common import Common

class StyleChecker:
    """
    风格检查器 [LOCKED]
    负责检查代码注释状态 (Draft/Locked)，并执行晋升 (Promote/Compile) 操作。
    """
    
    def __init__(self, use_target=True):
        self.file_path, self.scope = Common.get_full_target() if use_target else (None, None)

    def _read_content(self):
        if not self.file_path or not os.path.exists(self.file_path): return ""
        with open(self.file_path, 'r', encoding='utf-8') as f: return f.read()

    def _write_content(self, content):
        with open(self.file_path, 'w', encoding='utf-8') as f: f.write(content)

    def check(self):
        """
        检查文件内所有实体的文档状态
        Returns: JSON 列表 (Status: LOCKED, DRAFT, MISSING, UNLOCKED)
        """
        if not self.file_path: return
        content = self._read_content()
        
        entities = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name
                    doc = ast.get_docstring(node)
                    
                    status = "MISSING"
                    if doc:
                        if "[Unlock]" in doc:
                            status = "UNLOCKED (Pending Promote)"
                        elif "Gemini" in doc:
                            status = "DRAFT"
                        else:
                            status = "LOCKED"
                    
                    entities.append({
                        "name": name,
                        "type": type(node).__name__,
                        "line": node.lineno,
                        "status": status
                    })
        except Exception as e:
            print(f"解析错误: {e}")
            return

        import json
        print(json.dumps(entities, indent=2))

    def promote(self, selector=None):
        """
        晋升 (Compile/Promote)
        1. 去除注释中的 [Gemini] 标记。
        2. 去除注释中的 [Unlock] 标记 (Relock)。
        
        Args:
            selector (str): 实体名称 (None表示全部)
        """
        if not self.file_path: return
        content = self._read_content()
        lines = content.splitlines()

        # AST Based Replacement (Safer)
        target_nodes = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if selector and node.name != selector: continue
                    target_nodes.append(node)
        except: return

        promoted_count = 0
        
        for node in target_nodes:
            doc = ast.get_docstring(node)
            if not doc: continue
            
            # Check if needs promote
            has_gemini = "Gemini" in doc
            has_unlock = "[Unlock]" in doc
            
            if not (has_gemini or has_unlock): continue
            
            # Locate
            if not (node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                continue
                
            doc_node = node.body[0]
            s = doc_node.lineno - 1
            e = doc_node.end_lineno
            
            # Replace lines
            for i in range(s, e):
                orig = lines[i]
                # Clean tags
                new_line = orig.replace("[Gemini]", "").replace("[Unlock]", "")
                # Clean potential double spaces left behind
                new_line = new_line.replace("  ", " ") 
                
                if new_line != orig:
                    lines[i] = new_line
                    promoted_count += 1
        
        # Clean # [Unlock] comments (fallback style)
        clean_lines = []
        for l in lines:
            if "# [Unlock]" in l: continue # Remove the full line if it's just the tag
            clean_lines.append(l)
            
        self._write_content("\n".join(clean_lines))
        print(f"成功: 已晋升 (Promote/Relock) {promoted_count} 处文档。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    p_check = subparsers.add_parser("Check")
    p_prom = subparsers.add_parser("Promote"); p_prom.add_argument("--selector")

    args = parser.parse_args()
    checker = StyleChecker()
    
    if args.command == "Check": checker.check()
    elif args.command == "Promote": checker.promote(args.selector)
    else: parser.print_help()
