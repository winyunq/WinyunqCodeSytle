import os
import sys
import argparse
from Common import Common

def update_target(root=None, file=None, scope=None):
    """
    更新会话的目标状态 (Stateful)
    支持增量更新 (例如仅设置 scope)。
    
    Args:
        root (str): 项目根目录路径
        file (str): 目标文件路径 (相对于 Root)
        scope (str): 目标作用域 (Class/Namespace)
    """
    # 1. 加载现有状态
    state = Common.load_state()
    
    # 2. 更新 Root
    # 如果提供了 root，则更新它。这通常意味着新的上下文起点。
    if root:
        abs_root = os.path.abspath(root)
        if not os.path.exists(abs_root):
            # 尝试创建根目录
            try:
                os.makedirs(abs_root)
                print(f"[SetTarget] 创建根目录: {abs_root}")
            except Exception as e:
                print(f"[SetTarget] 创建根目录失败: {e}")
                return
        state["root"] = abs_root
        
        # 安全起见，如果变更了 Root，默认重置 File 和 Scope
        # 除非本次调用同时也指定了它们
        if not file: state["file"] = None
        if not scope: state["scope"] = None

    # 3. 更新 File
    if file:
        # File 路径通常相对于 Root
        state["file"] = file
        
        # 检查文件是否存在于 Root 下
        # 逻辑: 如果缺失，自动根据 Winyunq 规则创建 Gemini 草稿
        current_root = state["root"]
        full_path = os.path.join(current_root, file)
        
        if not os.path.exists(full_path):
            dir_name, base_name = os.path.split(full_path)
            
            # 计算 Gemini 变体名称
            gemini_name = Common.GEMINI_PREFIX + base_name if not base_name.startswith(Common.GEMINI_PREFIX) else base_name
            gemini_path = os.path.join(dir_name, gemini_name)
            
            target_create_path = gemini_path
            
            if os.path.exists(gemini_path):
                # 找到已存在的草稿，更新状态指向它
                state["file"] = os.path.relpath(gemini_path, current_root)
                print(f"[SetTarget] 发现现有草稿: {state['file']}")
            else:
                # 创建新草稿
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name)
                    
                with open(target_create_path, 'w', encoding='utf-8') as f:
                    f.write('"""\n[Gemini] Draft\n"""\n')
                
                # 更新状态
                state["file"] = os.path.relpath(target_create_path, current_root)
                print(f"[SetTarget] 创建新草稿: {state['file']}")
        
        # 如果变更了 File，重置 Scope (除非显式指定)
        if not scope: state["scope"] = None

    # 4. 更新 Scope
    if scope:
        state["scope"] = scope

    # 5. 保存并输出
    Common.save_state(state)
    print(f"当前目标 (Target):")
    print(f"  根目录 (Root):  {state['root']}")
    print(f"  文件 (File):    {state['file']}")
    print(f"  作用域 (Scope): {state['scope']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="设置编辑目标 (Stateful)")
    parser.add_argument("--root", help="设置项目根目录")
    parser.add_argument("--file", help="设置目标文件 (相对于 Root)")
    parser.add_argument("--scope", help="设置目标作用域 (Class/Function)")
    
    args = parser.parse_args()
    
    if not (args.root or args.file or args.scope):
        # 仅打印当前状态
        state = Common.load_state()
        print(f"当前目标 (Target):")
        print(f"  根目录 (Root):  {state['root']}")
        print(f"  文件 (File):    {state['file']}")
        print(f"  作用域 (Scope): {state['scope']}")
    else:
        update_target(args.root, args.file, args.scope)
