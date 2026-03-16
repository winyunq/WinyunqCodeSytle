
import os
import json
import re
import sys 

# Add current directory to path so we can import sibling scripts
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Common import ToolRegistry
from WriteCode import CodeWriter
from ReadCode import CodeReader
try:
    from CheckStyle import StyleChecker
except ImportError:
    StyleChecker = None

def get_payload():
    # Priority: 
    # 1. WinyunqCoding.md (Markdown with JSON block)
    # 2. WinyunqCoding.json (Pure JSON)
    
    # Check CWD (Execution Root)
    candidates = ["WinyunqCoding.md", "WinyunqCoding.json"]
    target_file = None
    cwd = os.getcwd()
    
    for c in candidates:
        p = os.path.join(cwd, c)
        if os.path.exists(p):
            target_file = p
            break
            
    if not target_file:
        print(f"Error: Could not find payload file (WinyunqCoding.md/json) in {cwd}")
        return None

    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if target_file.endswith(".md"):
            # Extract JSON from markdown
            # 1. Look for ```json ... ```
            match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            
            # 2. Look for just a JSON block validly
            # This is heuristic: find valid JSON object
            s = content.find('{')
            e = content.rfind('}')
            if s != -1 and e != -1:
                try:
                    return json.loads(content[s:e+1])
                except:
                    pass
            print("Error: Markdown file found but no valid JSON block extracted.")
            return None
        else:
            return json.loads(content)
            
    except Exception as e:
        print(f"Error parsing payload from {target_file}: {e}")
        return None
    return None

def main():
    payload = get_payload()
    if not payload: return # Error already printed

    # Parse Payload
    # Format 1: {"target": "WriteCode", "command": "Define", "params": {...}}
    # Format 2: {"tool": "WriteCode", ...}
    
    # Identify Tool
    tool_name = payload.get("target") or payload.get("tool") or payload.get("script")
    command = payload.get("command") or payload.get("action")
    params = payload.get("params") or payload.get("args") or {}

    sys.stderr.write(f"[RunSkill] Executing: {tool_name} -> {command}\n")
    
    # Instance Factory
    instance = None
    if tool_name == "WriteCode":
        instance = CodeWriter()
    elif tool_name == "ReadCode":
        instance = CodeReader()
    elif tool_name == "CheckStyle" and StyleChecker:
        instance = StyleChecker()
    # Add others...
    
    # Dispatch via Registry
    if instance:
        ToolRegistry.dispatch(tool_name, command, params, instance=instance)
    else:
        print(f"Error: Unknown tool or missing module for '{tool_name}'")

if __name__ == "__main__":
    main()
