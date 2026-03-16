import os
import sys
import argparse
import ast
import re
from Common import Common, WinyunqAction, ToolRegistry

class CodeWriter:
    """
    代码写入器 [LOCKED]
    支持 Declare, Define (严格块/双注释定位), Enable, Disable。
    支持从文件读取代码 (Gemini Workflow)。
    """
    
    def __init__(self, use_target=True):
        self.file_path, self.scope = Common.get_full_target() if use_target else (None, None)
    
    def _read_content(self):
        if not self.file_path or not os.path.exists(self.file_path): return ""
        with open(self.file_path, 'r', encoding='utf-8') as f: return f.read()

    def _write_content(self, content):
        with open(self.file_path, 'w', encoding='utf-8') as f: f.write(content)

    def _resolve_code_input(self, code_input):
        """
        解析代码输入：可以是直接的字符串，也可以是文件路径。
        如果是文件路径且文件名以 Gemini 开头，处理后删除文件。
        Returns: (content, should_shred_path)
        """
        if code_input and os.path.exists(code_input) and os.path.isfile(code_input):
            try:
                with open(code_input, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for shredding (Gemini prefix)
                filename = os.path.basename(code_input)
                if filename.lower().startswith("gemini"):
                    return content, code_input
                else:
                    return content, None
            except:
                # Fallback: maybe it's just a string that looks like a path?
                return code_input, None
        else:
            # Raw string
            # Handle standard escaped newlines if passed via shell
            return str(code_input).replace("\\n", "\n") if code_input else "", None

    @WinyunqAction("WriteCode", "Declare", "在文件末尾追加新对象声明")
    def declare(self, code):  # Renamed arg to 'code' to match convention
        code_block, shred_path = self._resolve_code_input(code)
        
        if not self.file_path: return
        try:
            tree = ast.parse(self._read_content())
            existing = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            input_tree = ast.parse(code_block)
            new_names = {n.name for n in ast.walk(input_tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        except Exception as e:
            print(f"解析错误: {e}")
            return

        if existing.intersection(new_names):
            print(f"冲突: {list(existing.intersection(new_names))}")
            return

        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write("\n" + code_block + "\n")
        
        preview = code_block.strip().splitlines()[0] if code_block.strip() else "(Empty)"
        if len(preview) > 50: preview = preview[:47] + "..."
        print(f"成功: 已追加至 {os.path.basename(self.file_path)} (Preview: {preview})")
        
        if shred_path:
            try: os.remove(shred_path); print(f"已清理临时文件: {shred_path}")
            except: pass

    @WinyunqAction("WriteCode", "Define", "覆写或插入函数实现")
    def define(self, name, code, mode="overwrite", 
               start_comment=None, end_comment=None):
        content, shred_path = self._resolve_code_input(code)
        
        if not self.file_path: return
        
        # 1. Prepare Content (Read & Calculate)
        full_text = self._read_content()
        lines = full_text.splitlines()
        
        # Locate
        target_node = None
        try:
            tree = ast.parse(full_text)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == name:
                    target_node = node
                    break
        except: 
            print("解析失败，无法定位函数")
            return

        if not target_node: print(f"错误: 函数 '{name}' 未找到"); return
        
        f_start = target_node.lineno - 1
        base_indent = target_node.col_offset
        f_end = f_start + 1
        # Determine function end
        for i in range(f_start + 1, len(lines)):
            l = lines[i]
            if not l.strip(): continue 
            if (len(l) - len(l.lstrip())) <= base_indent: break
            f_end = i + 1
            
        success_plan = False
        
        if not start_comment: # Full Overwrite (Global)
            if mode != "overwrite": print("Need start_comment for insert"); return
            
            if "def " + name in content:
                new_lines_seg = content.splitlines()
                # Apply change to buffer
                lines[f_start:f_end] = new_lines_seg
                success_plan = True
            else: print("Error: Provide full def properly."); return

        else: # Local Editing
            start_idx = -1
            clean_comm = start_comment.strip()
            for i in range(f_start, f_end):
                if clean_comm in lines[i]: start_idx=i; break
            
            if start_idx == -1: print("Start comment not found"); return
            
            code_line_idx = -1
            for i in range(start_idx+1, f_end):
                if lines[i].strip() and not lines[i].strip().startswith("#"): code_line_idx=i; break
            
            if code_line_idx == -1: print("No code below comment"); return
            
            code_indent = len(lines[code_line_idx]) - len(lines[code_line_idx].lstrip())
            end_idx = code_line_idx
            is_block = lines[code_line_idx].strip().endswith(":")
            
            if is_block:
                for i in range(code_line_idx+1, f_end):
                    l_next = lines[i]
                    if not l_next.strip(): continue
                    if (len(l_next)-len(l_next.lstrip())) <= code_indent: break
                    end_idx = i
            else:
                if mode == "overwrite" and end_comment:
                    for i in range(code_line_idx+1, f_end):
                        if end_comment.strip() in lines[i]: end_idx=i; break
            
            indent_str = " " * code_indent
            formatted = [indent_str + l.strip() for l in content.splitlines()]
            
            if mode == "overwrite":
                lines[start_idx : end_idx + 1] = formatted
                success_plan = True
            elif mode == "insert":
                if is_block: lines.insert(end_idx+1, "\n".join(formatted))
                else: lines.insert(end_idx+1, "\n".join(formatted))
                success_plan = True

        if not success_plan:
             print("Plan failed calculation.")
             return

        # 2. Check Lock & Write
        new_content_str = "\n".join(lines)
        
        try: 
            Common.enforce_lock(self.file_path)
            # If passed, just write
            self._write_content(new_content_str)
            print("Success (Authorized)")
            
        except PermissionError as e:
            print(f"Lock Collision: {e}")
            print("Launching UnlockGUI for confirmation...")
            try:
                from UnlockGUI import show_diff_dialog
                file_lines = self._read_content().splitlines() # Re-read original for clean diff? Or use 'full_text'
                # Actually show_diff_dialog expects full string.
                approved = show_diff_dialog(self.file_path, new_content_str)
                if approved:
                    print("User OVERRIDE: Writing changes...")
                    self._write_content(new_content_str)
                    print("Success (User Force)")
                else:
                    print("User REJECTED edit.")
            except ImportError:
                print("UnlockGUI not found. Cannot prompt user. Edit ABORTED.")
            except Exception as ex:
                print(f"GUI Error: {ex}")
        
        if shred_path:
            try: os.remove(shred_path); print(f"已清理临时文件: {shred_path}")
            except: pass

    @WinyunqAction("WriteCode", "Disable", "禁用功能 (Comment Out)")
    def disable(self, name): pass
    
    @WinyunqAction("WriteCode", "Enable", "启用功能 (Uncomment)")
    def enable(self, name): pass

if __name__ == "__main__":
    if "--manifest" in sys.argv:
        ToolRegistry.print_manifest("WriteCode")
        sys.exit(0)
        
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    p_decl = subparsers.add_parser("Declare")
    p_decl.add_argument("code", help="代码字符串 或 Gemini文件路径")
    
    p_def = subparsers.add_parser("Define")
    p_def.add_argument("name")
    p_def.add_argument("code", help="代码字符串 或 Gemini文件路径")
    p_def.add_argument("--mode", default='overwrite')
    p_def.add_argument("--start_comment")
    p_def.add_argument("--end_comment")

    p_en = subparsers.add_parser("Enable"); p_en.add_argument("name")
    p_dis = subparsers.add_parser("Disable"); p_dis.add_argument("name")

    args = parser.parse_args()
    writer = CodeWriter()
    
    if args.command == "Declare": writer.declare(args.code)
    elif args.command == "Define": writer.define(args.name, args.code, args.mode, args.start_comment, args.end_comment)
    elif args.command == "Enable": writer.enable(args.name)
    elif args.command == "Disable": writer.disable(args.name)
