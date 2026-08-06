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
    GEMINI_CONFIG_FILE = "Gemini_Config.json"
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
            "hpp_ext": ".hpp",
            "cpp_ext": ".cpp",
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
        path = os.path.join(self.root, self.GEMINI_CONFIG_FILE)

        default_state = {
            "work_path": os.path.join(self.root, self.settings.get("default_scope", ".")),
            "filters": [],
            "target_name": None,
            "pending_edit": None,
            "project_type": "Generic"
        }

        # UE5 自动发现逻辑
        source_path = os.path.join(self.root, "Source")
        if os.path.exists(source_path) and os.path.isdir(source_path):
            default_state["work_path"] = source_path
            default_state["project_type"] = "UE5"
            default_state["filters"] = ["Plugins", "Intermediate", "Saved", "Binaries", ".git", ".vs"]

        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    # 合并保存的状态，但如果 work_path 不存在了则降级
                    if not os.path.exists(saved_state.get("work_path", "")):
                        saved_state["work_path"] = default_state["work_path"]

                    # 动态同步设计
                    if saved_state.get("project_type") == "UE5":
                        self.settings["winyunqcodestyle"] = "UE5"

                    return saved_state
            except: pass

        return default_state

    def save_state(self, state):
        self.state = state
        path = os.path.join(self.root, self.GEMINI_CONFIG_FILE)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def resolve_file_by_name(self, name, preferred_ext=None):
        """
        [UNIVERSAL RESOLVER] 通过名称定位物理文件。
        支持 'A::B::C' (全称/缩写) 以及模糊匹配。

        索引逻辑权重：
        1. 完美匹配 (Exact Match, 忽略后缀/前缀)
        2. 层级包含匹配 (Hierarchy Match, e.g. DataAnalyzer 匹配 Class.hpp)
        3. 模糊内容匹配 (Context Match, e.g. analyze 匹配 Function.cpp)
        """
        if not name: return None
        parts = name.split("::")
        leaf_name = parts[-1].lower()
        work_path = self.state.get("work_path", self.root)
        prefix = self.settings.get("gemini_prefix", self.DEFAULT_GEMINI_PREFIX).lower()

        matches = [] # List of (score, path)

        for root, dirs, files in os.walk(work_path):
            # 过滤不需要的目录
            if any(f in root for f in self.state.get("filters", [])): continue

            for f in files:
                f_path = os.path.join(root, f)
                f_lower = f.lower()
                name_part = os.path.splitext(f_lower)[0]

                score = 0

                # 权重 1: 完美匹配文件名 (剥离前缀/UE5命名规范)
                def get_clean_name(np):
                    if np.startswith(prefix): np = np[len(prefix):]
                    if len(np) > 1 and np[1] == "_" and np[0] in "afuts": np = np[2:] # UE5 prefix
                    elif len(np) > 0 and np[0] in "afuts": np = np[1:]
                    return np

                clean_f = get_clean_name(name_part)
                clean_target = get_clean_name(leaf_name)

                if clean_f == clean_target:
                    score = 100
                elif clean_target in clean_f:
                    score = 50

                # 权重 2: 如果文件名不匹配，但在内容中 (模糊/内容探测)
                if score < 50:
                    try:
                        # 仅探测前 100 行，平衡效率
                        with open(f_path, 'r', encoding='utf-8') as f_obj:
                            sample = "".join([next(f_obj) for _ in range(100)]).lower()
                            if leaf_name in sample:
                                score = 20
                                # 如果包含完整的 A::B 路径，加分
                                if name.lower() in sample: score += 10
                    except: pass

                if score > 0:
                    matches.append((score, f_path))

        if not matches: return None

        # 按权重排序，权重相同时优先非 Gemini 文件
        def sort_key(item):
            s, p = item
            is_gemini = os.path.basename(p).lower().startswith(prefix)
            ext_score = 0
            if preferred_ext:
                ext_score = 5 if p.lower().endswith(preferred_ext.lower()) else -5
            return (s, ext_score, -1 if is_gemini else 1)

        matches.sort(key=sort_key, reverse=True)
        return matches[0][1]

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
                declared_params = {
                    item.get("name"): item
                    for item in attr._winyunq_meta.get("params", [])
                }
                if "name" in declared_params and not params.get("name"):
                    target_name = self.state.get("target_name")
                    if target_name:
                        params["name"] = target_name
                    elif declared_params["name"].get("required"):
                        return "Error: No object name was provided and no Target is active."
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
