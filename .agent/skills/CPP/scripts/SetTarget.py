import os
import argparse
from Common import Common

def set_target(root, file_path=None, scope=None):
    """
    设置当前工作上下文 [LOCKED]
    更新 Session State 以供后续工具使用。

    Args:
        root (str): 项目根目录
        file_path (str, optional): 相对文件路径
        scope (str, optional): 作用域名称 (函数/类名)
    """
    abs_root = os.path.abspath(root)
    state = {
        "root": abs_root,
        "file": file_path,
        "scope": scope
    }
    Common.save_state(state)
    
    print(f"当前目标 (Target):")
    print(f"  根目录 (Root):  {abs_root}")
    if file_path:
        print(f"  文件 (File):    {file_path}")
    if scope:
        print(f"  作用域 (Scope): {scope}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--file") # Optional now, but usually passed
    parser.add_argument("legacy_file", nargs='?', help="Legacy position arg support") 
    parser.add_argument("--scope")
    
    args = parser.parse_args()
    
    # Handle legacy positional arg
    fpath = args.file if args.file else args.legacy_file
    
    set_target(args.root, fpath, args.scope)