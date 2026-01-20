import os
import sys
import argparse
import re
import json
from Common import Common

class CppReader:
    """
    C++ 代码读取器 [LOCKED]
    支持 List (列出类/函数), Read (读取特定块)
    """
    def __init__(self, use_target=True):
        self.file_path, self.scope = Common.get_full_target() if use_target else (None, None)

    def _read_content(self):
        if not self.file_path or not os.path.exists(self.file_path): return ""
        with open(self.file_path, 'r', encoding='utf-8') as f: return f.read()

    def list_symbols(self):
        """
        Lists Classes and Functions in the file using Regex.
        Returns JSON list.
        """
        if not self.file_path: return
        content = self._read_content()
        symbols = []
        
        # 1. Classes / Structs
        # class Name { or struct Name {
        class_pattern = re.compile(r'\b(class|struct)\s+(\w+)\s*(?::[^\{]*)?\{')
        for m in class_pattern.finditer(content):
            symbols.append({"name": m.group(2), "type": m.group(1), "line": content[:m.start()].count('\n')+1})
            
        # 2. Functions
        # Type name(Args) {
        # Exclude regex matches inside strings or comments? Simple regex is flawed but acceptable for now.
        # \w+ \w+\(  --> Type Name(
        func_pattern = re.compile(r'\b(\w[\w:<>,]*[*&]?)\s+(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?::[^\{]*)?\{')
        for m in func_pattern.finditer(content):
            # Filter keyword hits like "if (", "while ("
            name = m.group(2)
            if name not in ["if", "while", "for", "switch", "catch"]:
                 symbols.append({"name": name, "type": "function", "return_type": m.group(1), "line": content[:m.start()].count('\n')+1})
        
        symbols.sort(key=lambda x: x['line'])
        print(json.dumps(symbols, indent=2))

    def read_block(self, name):
        """
        Reads the code block for a specific function/class.
        """
        if not self.file_path: return
        content = self._read_content()
        
        # Brace counting logic similar to WriteCode
        pattern = re.compile(rf'\b{re.escape(name)}\s*(?:\(.*\)|{{)') # Match func( or class {
        match = pattern.search(content)
        if not match:
             # Try simple text match?
             pass
        else:
             # Just heuristic: find '{' after match
             brace_idx = content.find('{', match.end()-1) # Search near end
             if brace_idx != -1:
                 cnt = 1
                 for i in range(brace_idx+1, len(content)):
                     if content[i] == '{': cnt+=1
                     elif content[i] == '}': cnt-=1
                     if cnt == 0:
                         print(content[match.start() : i+1])
                         return
        print(f"Block '{name}' not found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    p_lst = subparsers.add_parser("List")
    
    p_read = subparsers.add_parser("Read")
    p_read.add_argument("name")

    args = parser.parse_args()
    reader = CppReader()
    
    if args.command == "List": reader.list_symbols()
    elif args.command == "Read": reader.read_block(args.name)
