import os
import sys
import argparse
from Common import Common

def check_style(file_path):
    """
    Winyunq C++ 风格检查 [LOCKED]
    """
    if not os.path.exists(file_path):
        print("ERROR: File not found")
        return

    is_header = file_path.endswith(('.hpp', '.h'))
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    filename = os.path.basename(file_path)
    
    # 1. Basic check
    has_comments = "///" in content or "/**" in content
    if not has_comments:
        print(f"[CheckStyle] {filename}: ERROR (No Winyunq comments found)")
        # In Winyunq Protocol, No Comments = Error.
        return

    # 2. Check Lock (Common implements regex)
    if Common.is_locked(content, is_header):
        print(f"[CheckStyle] {filename}: LOCKED (Formal comments present)")
    else:
        print(f"[CheckStyle] {filename}: DRAFT (Gemini or missing formal tags)")

def promote(file_path):
    # Logic to strip [Unlock] / [Gemini] from C++ comments?
    # Keeping it simple for now (Read Only Check)
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    p_chk = subparsers.add_parser("Check")
    p_chk.add_argument("file", nargs='?') # Optional if using set_target logic, but here we require file for simplicity or update
    
    p_prom = subparsers.add_parser("Promote")

    args = parser.parse_args()
    
    # Support direct call "CheckStyle.py file" check for backward compat?
    # New standard: "CheckStyle.py Check --file ..." via SetTarget context
    
    # Let's assume standard usage:
    # python CheckStyle.py Check
    
    if args.command == "Check":
        # Get target from Common if not provided?
        fpath, _ = Common.get_full_target()
        if fpath: check_style(fpath)
        else: print("No target set")