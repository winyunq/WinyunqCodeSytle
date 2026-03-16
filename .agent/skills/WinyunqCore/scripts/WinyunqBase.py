import os
import json
import re
import sys
import subprocess

class WinyunqBase:
    """
    Winyunq 核心基座 (WinyunqBase) [STRATEGIC HUB]
    实现“战略锚定路径，战术去路径化”的核心逻辑。
    """
    SESSION_FILE = ".session_context.json"
    SETTINGS_FILE = ".agent/settings.json"
    DEFAULT_GEMINI_PREFIX = "Gemini_"

    def __init__(self, **kwargs):
        self.root = self.get_root()
        self.settings = self.load_settings()
        self.state = self.load_state()
        self.skills_root = os.path.join(self.root, ".agent", "skills")
        self.doxygen_style = self.load_doxygen_style()

    def load_doxygen_style(self):
        path = os.path.join(self.root, "config", "DoxygenStyle.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {
            "column_align": 40,
            "column_param_start": 15,
            "indent_width": 4,
            "block_comment_indent": True,
            "doc_block_target": "hpp",
            "tokens": {
                "extend": "@extend",
                "brief": "@brief",
                "details": "@details",
                "param": "@param",
                "return": "@return"
            }
        }

    def get_root(self):
        current = os.path.abspath(os.getcwd())
        while len(current) > 4:
            if os.path.exists(os.path.join(current, ".agent")): return current
            current = os.path.dirname(current)
        return os.getcwd()

    def load_settings(self):
        path = os.path.join(self.root, self.SETTINGS_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {
            "gemini_prefix": self.DEFAULT_GEMINI_PREFIX,
            "formal_prefix": "",
            "default_scope": ".",
            "winyunqcodestyle": "CPP"
        }

    def load_state(self):
        path = os.path.join(self.root, self.SESSION_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f: 
                    return json.load(f)
            except: pass
        return {
            "work_path": os.path.join(self.root, self.settings.get("default_scope", ".")),
            "filters": [],
            "target_name": None
        }

    def save_state(self, state):
        self.state = state
        path = os.path.join(self.root, self.SESSION_FILE)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    def resolve_file_by_name(self, name, preferred_ext=None):
        """
        [AUTOMATED RESOLUTION] 通过名称定位物理文件。
        支持 'A::B::C' 形式的层级路径。
        """
        if not name: return None
        parts = name.split("::")
        leaf_name = parts[-1].lower()
        work_path = self.state.get("work_path", self.root)
        prefix = self.settings.get("gemini_prefix", self.DEFAULT_GEMINI_PREFIX).lower()
        
        matches = []
        for root, dirs, files in os.walk(work_path):
            for f in files:
                f_lower = f.lower()
                # 匹配逻辑：名称相同 (忽略后缀) 或者是 Gemini 镜像
                name_part = os.path.splitext(f_lower)[0]
                if name_part == leaf_name or name_part == (prefix + leaf_name):
                    matches.append(os.path.join(root, f))
        
        if not matches: return None
        
        # 严格后缀匹配逻辑
        if preferred_ext:
            pe = preferred_ext.lower()
            if not pe.startswith("."): pe = "." + pe
            
            # 1. 优先非 Gemini 正式文件
            for m in matches:
                b = os.path.basename(m).lower()
                if b.endswith(pe) and not b.startswith(prefix): return m
            # 2. 其次 Gemini 镜像
            for m in matches:
                if m.lower().endswith(pe): return m
            
            # 若指定了后缀但没找到对应文件，必须返回 None 而不能返回其他后缀的文件
            return None
        
        # 无后缀要求时，返回第一个匹配项
        return matches[0]

    def get_write_path(self, original_path):
        prefix = self.settings.get("gemini_prefix", self.DEFAULT_GEMINI_PREFIX)
        dirname, basename = os.path.split(original_path)
        if not basename.startswith(prefix):
            basename = f"{prefix}{basename}"
        return os.path.join(dirname, basename)

    def invoke(self, action_name, params):
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, "_winyunq_meta") and attr._winyunq_meta["action"] == action_name:
                if "name" in params and not params["name"]:
                    params["name"] = self.state.get("target_name")
                return attr(**params)
        return f"Error: Action '{action_name}' not found."

    def get_manifest(self):
        manifest = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, "_winyunq_meta"):
                meta = attr._winyunq_meta
                manifest[meta["action"]] = {
                    "description": meta["doc"],
                    "params": meta["params"]
                }
        return manifest

def WinyunqAction(action_name, description="", params=None):
    def decorator(func):
        func._winyunq_meta = {"action": action_name, "doc": description, "params": params or []}
        return func
    return decorator
