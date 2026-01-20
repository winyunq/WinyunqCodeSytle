import os
import re
import json

class Common:
    GEMINI_PREFIX = "Gemini_"
    SESSION_FILE = ".session_context.json"
    
    # Regex (Docstring)
    REGEX_LOCKED_DOCSTRING = re.compile(r'("""|\'\'\')(?s:.*?)(?<!Gemini)(?s:.*?)\1')

    @staticmethod
    def get_gemini_path(file_path):
        dirname, basename = os.path.split(file_path)
        if basename.startswith(Common.GEMINI_PREFIX):
            return file_path
        return os.path.join(dirname, Common.GEMINI_PREFIX + basename)

    @staticmethod
    def is_locked(content):
        # 0. Check for explicit Unlock tag (High Priority Bypass)
        if "[Unlock]" in content:
             # Warning: simple check. Better: confirm it's in a comment?
             # For now, strict tag anywhere in content implies active edit session.
             # Or better: check per block in WriteCode. 
             # But Common.is_locked is usually file-level or block level.
             # If we return False here, enforce_lock passes.
             return False

        # 1. Check Docstrings (API Lock)
        docstrings = re.findall(r'("""|\'\'\')((?:.|\n)*?)\1', content)
        for _, inner_text in docstrings:
            if "Gemini" not in inner_text:
                return True 

        # 2. Check Hash Comments (Impl Lock)
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                comment_text = stripped[1:]
                if "Gemini" not in comment_text:
                    return True
        return False

    @staticmethod
    def enforce_lock(file_path):
        filename = os.path.basename(file_path)
        if filename.startswith(Common.GEMINI_PREFIX):
            return False 
        
        if not os.path.exists(file_path):
            return False
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if Common.is_locked(content):
            # Double check: if [Unlock] is present, is_locked returns False.
            # So if we are here, it's truly Locked.
            raise PermissionError(f"BLOCK: File '{filename}' is LOCKED by Winyunq Protocol (Formal Docstring or # found). Request Unlock first.")
        return False

    # --- Session State Management ---
    @staticmethod
    def load_state():
        """Loads the current session state (Root, File, Scope)."""
        if os.path.exists(Common.SESSION_FILE):
            try:
                with open(Common.SESSION_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"root": os.getcwd(), "file": None, "scope": None}

    @staticmethod
    def save_state(state):
        """Saves the session state."""
        with open(Common.SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def get_full_target():
        """Returns (full_path, scope) based on state."""
        state = Common.load_state()
        root = state.get("root", os.getcwd())
        rel_file = state.get("file")
        scope = state.get("scope")
        
        if rel_file:
            return os.path.join(root, rel_file), scope
        return None, scope
