import os
import sys
import argparse
import ast
import tkinter as tk
from tkinter import messagebox

def inject_unlock_tag(file_path, function_name=None):
    """
    Injects [Unlock] tag into the docstring of the file or specific function.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.splitlines()

    target_node = None
    
    try:
        tree = ast.parse(content)
        # Search Scope
        if function_name:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == function_name:
                    target_node = node
                    break
        else:
            # File level? Module docstring
            if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, (ast.Str, ast.Constant)):
                target_node = tree # Module level handling is complex in AST node mapping without node visitor
                # Let's stick to modifying the first docstring found or appending it
                pass
    except SyntaxError:
        print("Error: Syntax Error parsing file.")
        return False

    if not target_node and function_name:
        print(f"Error: Function {function_name} not found.")
        return False

    # Logic: Find Docstring Line
    doc_node = None
    
    if target_node:
        doc = ast.get_docstring(target_node)
        if doc:
            # Locate node
            if isinstance(target_node, ast.Module):
                # special case
                doc_node = target_node.body[0]
            elif target_node.body and isinstance(target_node.body[0], ast.Expr) and isinstance(target_node.body[0].value, (ast.Str, ast.Constant)):
                doc_node = target_node.body[0]
        else:
            # No docstring, we should add one? 
            # Or assume we can just modify file?
            # If no docstring, it's technically "Draft" or "Error" state anyway (unless Impl comments lock it).
            # But the user wants explicit [Unlock].
            # Getting complicated. 
            # Simplest Winyunq Protocol: If Locked (has docstring), we append [Unlock].
            pass

    if doc_node:
        # Edit existing docstring
        s = doc_node.lineno - 1
        e = doc_node.end_lineno
        
        # Determine indentation
        indent = ""
        first_line = lines[s]
        indent = first_line[:len(first_line)-len(first_line.lstrip())]
        
        # Insert [Unlock] into the docstring text
        # We can just insert it at line s (inside the quotes?)
        # Or Just append before closing quotes.
        
        # Read the block
        block = lines[s:e]
        # Find closing quotes
        last_line = block[-1]
        if '"""' in last_line:
             lines[s + len(block) - 1] = last_line.replace('"""', '[Unlock] """', 1) # Append before end
        elif "'''" in last_line:
             lines[s + len(block) - 1] = last_line.replace("'''", "[Unlock] '''", 1)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        print(f"Success: Unlocked {function_name if function_name else file_path}")
        return True
    
    else:
        print("Warning: No docstring found. Code might be Draft already? Attempting global unlock injection.")
        # Fallback: Just append a comment [Unlock] to line 0 or before function
        if function_name and target_node:
             s = target_node.lineno - 1
             indent = " " * target_node.col_offset
             lines.insert(s, f"{indent}# [Unlock]")
             with open(file_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
             return True
        else:
             lines.insert(0, "# [Unlock]")
             with open(file_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
             return True
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to file")
    parser.add_argument("--function", help="Function/Class name", default=None)
    args = parser.parse_args()

    file_path = args.file
    func_name = args.function
    
    if not os.path.exists(file_path):
        print("File not found")
        sys.exit(1)

    # 1. UI Request
    root = tk.Tk()
    root.withdraw() # Hide main window
    
    title = f"AI Request: Unlock {func_name if func_name else os.path.basename(file_path)}?"
    msg = f"AI Agent requests permission to EDIT/UNLOCK:\n\nFile: {file_path}\nObject: {func_name if func_name else 'Entire File'}\n\nClick Yes to Inject [Unlock] tag."
    
    result = messagebox.askyesno("Winyunq Unlock Protocol", msg)
    
    if result:
        # 2. Execute Unlock
        success = inject_unlock_tag(file_path, func_name)
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("Request Denied by User")
        sys.exit(1)

if __name__ == "__main__":
    main()
