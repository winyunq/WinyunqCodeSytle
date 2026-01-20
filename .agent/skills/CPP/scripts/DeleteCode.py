import os
import sys
import argparse
from Common import Common

def delete_code(file_path):
    """
    Deletes a file if not locked. 
    (Future: Support deleting specific entities inside file)
    """
    Common.enforce_lock(file_path)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"[DeleteCode] Deleted {file_path}")
    else:
        print(f"[DeleteCode] File not found {file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Target file to delete")
    args = parser.parse_args()
    
    try:
        delete_code(args.file)
    except PermissionError as e:
        print(e)
        sys.exit(1)
