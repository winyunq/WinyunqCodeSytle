class Common:
    GEMINI_PREFIX = "Gemini_"
    SESSION_FILE = ".session_context.json"
    
    # C++ Regex (HPP/CPP)
    REGEX_LOCKED_HPP = re.compile(r'/\*\*(?:(?!\*/).)*?@brief\s+(?!.*Gemini).*?\*/', re.DOTALL)
    REGEX_LOCKED_CPP = re.compile(r'///\s*@brief\s+(?!.*Gemini).*')

    @staticmethod
    def get_gemini_path(file_path):
        dirname, basename = os.path.split(file_path)
        if basename.startswith(Common.GEMINI_PREFIX):
            return file_path
        return os.path.join(dirname, Common.GEMINI_PREFIX + basename)

    @staticmethod
    def is_locked(content, is_header=False):
        if is_header:
            return bool(Common.REGEX_LOCKED_HPP.search(content))
        else:
            return bool(Common.REGEX_LOCKED_CPP.search(content))

    @staticmethod
    def enforce_lock(file_path):
        filename = os.path.basename(file_path)
        if filename.startswith(Common.GEMINI_PREFIX):
            return False 
        
        if not os.path.exists(file_path):
            return False
            
        is_header = file_path.endswith(('.hpp', '.h'))
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if Common.is_locked(content, is_header):
            raise PermissionError(f"BLOCK: File '{filename}' is LOCKED by Winyunq Protocol (Formal @brief found).")
        return False

    @staticmethod
    def load_state():
        if os.path.exists(Common.SESSION_FILE):
            try:
                with open(Common.SESSION_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {"root": os.getcwd(), "file": None, "scope": None}

    @staticmethod
    def save_state(state):
        with open(Common.SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def get_full_target():
        state = Common.load_state()
        root = state.get("root", os.getcwd())
        rel_file = state.get("file")
        scope = state.get("scope")
        if rel_file:
            return os.path.join(root, rel_file), scope
        return None, scope
