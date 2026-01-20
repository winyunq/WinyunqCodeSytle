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
        if os.path.exists(code_input) and os.path.isfile(code_input):
            try:
                with open(code_input, 'r', encoding='utf-8') as f: content = f.read()
                filename = os.path.basename(code_input)
                if filename.lower().startswith("gemini"): return content, code_input
                else: return content, None
            except: return code_input, None
        return code_input.replace("\\n", "\n"), None

    def _find_function_block(self, content, name):
        """
        Locates a C++ function block by name.
        Simple heuristic: look for `Type name(` or `name(` followed by `{`.
        Returns: (start_index, end_index) or None
        """
        # Regex to find function definition header
        # Pattern: \bname\s*\(.*?\)\s*(?:const)?\s*\{
        # Note: This is fragile for complex C++, but compliant with Winyunq style.
        pattern = re.compile(rf'\b{re.escape(name)}\s*\(.*?\)[^{{]*\{{', re.DOTALL)
        match = pattern.search(content)
        
        if not match: return None
        
        start_idx = match.start()
        # Brace counting from the opening brace
        brace_start = match.end() - 1 
        if content[brace_start] != '{': return None # Should be due to regex

        cnt = 1
        end_idx = -1
        for i in range(brace_start + 1, len(content)):
            if content[i] == '{': cnt += 1
            elif content[i] == '}': cnt -= 1
            
            if cnt == 0:
                end_idx = i + 1
                break
        
        if end_idx != -1:
            return (start_idx, end_idx)
        return None

    def declare(self, code_arg):
        code, shred = self._resolve_code_input(code_arg)
        if not self.file_path: return

        # For Declare, usually simply append to HPP or CPP.
        # Ideally check for duplicates but Regex is hard. 
        # Just append with a newline separator.
        
        current = self._read_content()
        # Simple duplicte check: string match
        if code.strip() in current:
             print("Skipped: Code already exists.")
        else:
             # If HPP, insert before last #endif or } ??
             # Too complex to guess. Append to end is safest for now, user can move it.
             # Or append before last closing brace if Class scope?
             
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
            print(f"Error: Function {name} not found for definition.")
            return

        s, e = span
        
        # Lock check for the specific block?
        # Check comments immediately preceding s
        # (Simplified: File Lock is checked at top. Detailed logic would check /// here.)
        
        if mode == "overwrite":
            # Replace [s:e] with new code
            new_content = content[:s] + code + content[e:]
            self._write_content(new_content)
            print("Success: Function definition overwritten.")
        
        if shred:
            try: os.remove(shred)
            except: pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    p_dec = subparsers.add_parser("Declare")
    p_dec.add_argument("code")
    
    p_def = subparsers.add_parser("Define")
    p_def.add_argument("name")
    p_def.add_argument("code")
    p_def.add_argument("--mode", default="overwrite")

    args = parser.parse_args()
    writer = CppWriter()
    
    if args.command == "Declare": writer.declare(args.code)
    elif args.command == "Define": writer.define(args.name, args.code, args.mode)
