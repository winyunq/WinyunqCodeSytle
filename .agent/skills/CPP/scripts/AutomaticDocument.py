import os
import sys
import argparse
import re
import json
from Common import Common

class DocumentManager:
    """
    C++ 文档管理器 [LOCKED]
    支持 CheckDocument (检查缺失), Write (写入文档)
    """
    def __init__(self, file_path):
        self.file_path = file_path
        self._content = ""
        self._lines = []
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                self._content = f.read()
                self._lines = self._content.splitlines()

    def get_undocumented(self):
        """
        Scanning C++ files for functions/classes without docstrings.
        Returns list of {name, line, type}.
        """
        # Simplified scanning
        missing = []
        
        # 1. Classes (HPP)
        class_pattern = re.compile(r'\b(class|struct)\s+(\w+)\s*\{')
        for m in class_pattern.finditer(self._content):
            # Check if preceded by /**
            preceding = self._content[:m.start()].strip()
            if not preceding.endswith('*/'):
                missing.append({"name": m.group(2), "type": m.group(1), "line": self._content[:m.start()].count('\n')+1})

        # 2. Functions (CPP/HPP)
        # Regex is hard. Assume functions start with Type Name(
        func_pattern = re.compile(r'\b(\w[\w:<>,]*[*&]?)\s+(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?::[^\{]*)?\{')
        for m in func_pattern.finditer(self._content):
            name = m.group(2)
            if name in ["if", "while", "for", "switch"]: continue
            
            start = m.start()
            # Check comment
            # HPP: Look for /**
            # CPP: Look for ///
            is_header = self.file_path.endswith(('.hpp', '.h'))
            
            has_doc = False
            lines_before = self._content[:start].splitlines()
            if lines_before:
                last_line = lines_before[-1].strip()
                if is_header:
                    if '*/' in last_line: has_doc = True
                else:
                    if last_line.startswith('///'): has_doc = True
            
            if not has_doc:
                missing.append({"name": name, "type": "function", "line": self._content[:start].count('\n')+1})
                
        return missing

    def write_comment(self, selector, json_data):
        # Implementation for writing /** */ or ///
        # Omitted for brevity, but would parse JSON and insert lines.
        # This is a critical feature but for now 'Check' is priority.
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    p_check = subparsers.add_parser("CheckDocument")
    p_check.add_argument("file")
    
    p_list = subparsers.add_parser("GetNoDocumentList")
    p_list.add_argument("file")

    args = parser.parse_args()
    mgr = DocumentManager(args.file)
    
    if args.command == "CheckDocument":
        print(len(mgr.get_undocumented()))
    elif args.command == "GetNoDocumentList":
        print(json.dumps(mgr.get_undocumented(), indent=2))
