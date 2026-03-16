import os
import sys
import json
import importlib.util

def run_mission():
    """
    统一任务执行器 [STRATEGIC DISPATCHER]
    从 WinyunqCoding.json 加载指令，并根据 winyunqcodestyle 调度 sub-skill。
    """
    payload_file = "WinyunqCoding.json"
    if not os.path.exists(payload_file):
        print("Error: No WinyunqCoding.json found.")
        return

    try:
        with open(payload_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return

    tool_name = payload.get("tool")
    action_name = payload.get("action") or payload.get("command")
    params = payload.get("params", {})
    
    # 核心路径与子技能路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 识别风格: 优先自 Payload, 其次自 Settings (由类加载)
    style = payload.get("winyunqcodestyle")
    
    # 寻址策略: 
    # 1. 尝试 {root}/.agent/skills/{style}/scripts/{tool}.py
    # 2. 回退 {root}/.agent/skills/WinyunqCore/scripts/{tool}.py
    
    root = os.path.join(script_dir, "..", "..", "..", "..")
    sub_skill_path = os.path.abspath(os.path.join(script_dir, "..", "..", style, "scripts", f"{tool_name}.py")) if style else None
    core_path = os.path.join(script_dir, f"{tool_name}.py")
    
    target_path = sub_skill_path if (sub_skill_path and os.path.exists(sub_skill_path)) else core_path

    if not os.path.exists(target_path):
        print(f"Error: Tool '{tool_name}' not found at {target_path}")
        return

    try:
        spec = importlib.util.spec_from_file_location(tool_name, target_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, tool_name):
            inst = getattr(module, tool_name)()
            result = inst.invoke(action_name, params)
            print("--- MCP OUTPUT ---")
            print(result)
            print("------------------")
        else:
            print(f"Error: Class '{tool_name}' not found in its script.")
    except Exception as e:
        print(f"Execution Error: {str(e)}")

if __name__ == "__main__":
    run_mission()
