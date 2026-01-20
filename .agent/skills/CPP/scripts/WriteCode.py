import os
import sys
import argparse
import re
from Common import Common

class CppWriter:
    """
    C++ 代码写入器 [LOCKED]
    支持基于 Regex/Brace-Counting 的 C++ 代码 Declare/Define 操作。
    """
    
    def __init__(self, use_target=True):
        self.file_path, self.scope = Common.get_full_target() if use_target else (None, None)

    def _read_content(self):
        if not self.file_path or not os.path.exists(self.file_path): return ""
        with open(self.file_path, 'r', encoding='utf-8') as f: return f.read()

    def _write_content(self, content):
        with open(self.file_path, 'w', encoding='utf-8') as f: f.write(content)

    def _resolve_code_input(self, code_input):
        # Support Gemini autoshred
        if os.path.exists(code_input) and os.path.isfile(code_input):
            try:
                with open(code_input, 'r', encoding='utf-8') as f: content = f.read()
                filename = os.path.basename(code_input)
                if filename.lower().startswith("gemini"): return content, code_input
                else: return content, None
            except: return code_input, None
        return code_input.replace("\\n", "\n"), None

    def _find_function_block(self, content, name):
        # Regex to find function definition header: name(...) {
        # Fragile heuristic but fits Agent usage
        pattern = re.compile(rf'\b{re.escape(name)}\s*\(.*?\)[^{{]*\{{', re.DOTALL)
        match = pattern.search(content)
        if not match: return None
        
        start_idx = match.start()
        brace_start = match.end() - 1 
        
        cnt = 1
        end_idx = -1
        # Simple brace counting
        for i in range(brace_start + 1, len(content)):
            if content[i] == '{': cnt += 1
            elif content[i] == '}': cnt -= 1
            if cnt == 0:
                end_idx = i + 1
                break
        
        if end_idx != -1: return (start_idx, end_idx)
        return None

    def declare(self, code_arg):
        code, shred = self._resolve_code_input(code_arg)
        if not self.file_path: return

        current = self._read_content()
        if code.strip() in current:
             print("Skipped: Code already exists.")
        else:
             with open(self.file_path, 'a', encoding='utf-8') as f:
                 f.write("\n" + code + "\n")
             print(f"Success: Appended declaration.")

        if shred:
            try: os.remove(shred)
            except: pass

    def define(self, name, code_arg, mode="overwrite"):
        code, shred = self._resolve_code_input(code_arg)
        if not self.file_path: return
        
        try: Common.enforce_lock(self.file_path)
        except PermissionError as e: print(e); return
        
        content = self._read_content()
        span = self._find_function_block(content, name)
        
        if not span:
            # Fallback: Just append if define not found? Or Error?
            # User might want to add new definition.
            # But 'Define' implies existing or specific placement. 'Declare' is generic append.
            # Let's error for safety.
            print(f"Error: Function {name} not found for definition override.")
            return

        s, e = span
        if mode == "overwrite":
            new_content = content[:s] + code + content[e:]
            self._write_content(new_content)
            print("Success: Function definition overwritten.")
        
        if shred:
            try: os.remove(shred)
            except: pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    p_dec = subparsers.add_parser("Declare"); p_dec.add_argument("code")
    p_def = subparsers.add_parser("Define"); p_def.add_argument("name"); p_def.add_argument("code"); p_def.add_argument("--mode", default="overwrite")

    args = parser.parse_args()
    writer = CppWriter()
    
    if args.command == "Declare": writer.declare(args.code)
    elif args.command == "Define": writer.define(args.name, args.code, args.mode)
