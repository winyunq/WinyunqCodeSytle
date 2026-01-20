import os
import sys
import argparse
import re
import tkinter as tk
from tkinter import messagebox
from Common import Common

def inject_unlock_tag(file_path, function_name=None):
    """
    Injects [Unlock] tag into C++ files.
    """
    if not os.path.exists(file_path): return False
    with open(file_path, 'r', encoding='utf-8') as f: content = f.read()

    # If no function name, Global Unlock
    if not function_name:
        if "[Unlock]" not in content:
            new_content = "// [Unlock]\n" + content
            with open(file_path, 'w', encoding='utf-8') as f: f.write(new_content)
            print("Global Unlock Injection Success.")
            return True
        return True

    # Locate Function
    # Use simpler regex than WriteCode for robust loose matching
    # Look for "name("
    pattern = re.compile(rf'\b{re.escape(function_name)}\s*\(', re.DOTALL)
    match = pattern.search(content)
    
    if not match:
        print(f"Function {function_name} not found. Fallback to global unlock?")
        # Fallback to global
        return inject_unlock_tag(file_path, None)
        
    start_idx = match.start()
    
    # Check preceding lines for comments
    # We want to find the END of the comment block immediately before start_idx
    
    # Strategy: inject `[Unlock]` into the line above start_idx?
    # Or strict comment structure?
    
    # Simple: Just insert `// [Unlock]` line before the function definition.
    # This satisfies Common.is_locked() check which looks for [Unlock] anywhere in file/block?
    # Wait, Common.is_locked returned False if "[Unlock]" is IN CONTENT.
    # My Common.py (Step 334) implementation:
    # if "[Unlock]" in content: return False
    
    # So actually, putting it ANYWHERE works.
    # But for "Style", putting it in the docstring is best.
    
    # Let's try to put it inside /** */ if exists key.
    
    preceding = content[:start_idx]
    if '*/' in preceding:
        # Might be the docstring.
        last_comment_end = preceding.rfind('*/')
        # Check distance
        distance = content[last_comment_end+2 : start_idx]
        if not distance.strip(): # Only whitespace between comment and func
            # Inject inside
            new_content = content[:last_comment_end] + " [Unlock]" + content[last_comment_end:]
            with open(file_path, 'w', encoding='utf-8') as f: f.write(new_content)
            print(" injected into Docstring.")
            return True

    # Else insert // [Unlock] above
    lines = content.splitlines()
    line_idx = content[:start_idx].count('\n')
    lines.insert(line_idx, "// [Unlock]")
    with open(file_path, 'w', encoding='utf-8') as f: f.write("\n".join(lines))
    print("Injected // [Unlock] tag.")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--function", default=None)
    args = parser.parse_args()

    file_path = args.file
    func_name = args.function
    
    if not os.path.exists(file_path): sys.exit(1)

    root = tk.Tk(); root.withdraw()
    
    msg = f"AI Request EDIT C++:\n{file_path}\nTarget: {func_name or 'Global'}\n\nApprove?"
    if messagebox.askyesno("Winyunq C++ Unlock", msg):
        if inject_unlock_tag(file_path, func_name): sys.exit(0)
        else: sys.exit(1)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
