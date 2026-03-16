import os
import sys
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import subprocess

try:
    from WinyunqBase import WinyunqBase
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqBase

class SkillGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Winyunq Strategic Commander (V5 - Scope Based)")
        self.root.geometry("1100x850")
        
        self.core = WinyunqBase()
        self.manifest_cache = {}
        self.setup_ui()
        self.refresh_skills()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        
        # --- Strategic Banner ---
        strategy = ttk.LabelFrame(main, text="战略设定 (Strategic Scope)", padding=10)
        strategy.pack(fill=tk.X, pady=5)
        
        self.scope_label = ttk.Label(strategy, text="当前工作路径: [未加载]", font=("Segoe UI", 9, "bold"))
        self.scope_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(strategy, text="代码风格:").pack(side=tk.LEFT, padx=5)
        self.style_var = tk.StringVar(value="CPP")
        self.style_combo = ttk.Combobox(strategy, textvariable=self.style_var, values=["CPP", "Python", "WinyunqCore"], width=12)
        self.style_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(strategy, text="同步 Scope", command=self.sync_scope).pack(side=tk.RIGHT)

        # --- Tactical Control ---
        tactical = ttk.LabelFrame(main, text="战术指令 (Tactical Control)", padding=10)
        tactical.pack(fill=tk.X, pady=5)
# ... lines continued in next chunk ...
        
        ttk.Label(tactical, text="支柱:").grid(row=0, column=0, padx=5)
        self.tool_var = tk.StringVar()
        self.tool_combo = ttk.Combobox(tactical, textvariable=self.tool_var, state="readonly")
        self.tool_combo.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.tool_combo.bind("<<ComboboxSelected>>", self.on_tool_selected)
        
        ttk.Label(tactical, text="指令:").grid(row=0, column=2, padx=5)
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(tactical, textvariable=self.action_var, state="readonly")
        self.action_combo.grid(row=0, column=3, sticky=tk.EW, padx=5)
        self.action_combo.bind("<<ComboboxSelected>>", self.on_action_selected)
        
        tactical.columnconfigure(1, weight=1)
        tactical.columnconfigure(3, weight=1)

        # --- Parameters (No Path Input!) ---
        self.param_frame = ttk.LabelFrame(main, text="指令参数 (Taxonomy Driven)", padding=10)
        self.param_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.param_entries_frame = ttk.Frame(self.param_frame)
        self.param_entries_frame.pack(fill=tk.BOTH, expand=True)
        self.param_inputs = {}

        # --- Command Generator ---
        gen = ttk.Frame(main, padding=5)
        gen.pack(fill=tk.X)
        ttk.Button(gen, text="▶ 执行战术指令", command=self.execute_mission).pack(side=tk.RIGHT, padx=5)

        # --- MCP Payload Preview (Request) ---
        payload_audit = ttk.LabelFrame(main, text="MCP 请求审计 (Request Payload)", padding=5)
        payload_audit.pack(fill=tk.X, pady=5)
        self.payload_view = tk.Text(payload_audit, height=3, font=("Consolas", 10), bg="#2d2d2d", fg="#ffffff")
        self.payload_view.pack(fill=tk.X)

        # --- AI Perspective (Response) ---
        response_audit = ttk.LabelFrame(main, text="AI 视角审计 (Response / AI Context)", padding=5)
        response_audit.pack(fill=tk.X, pady=5)
        self.response_view = tk.Text(response_audit, height=6, font=("Consolas", 10), bg="#1c1c2b", fg="#00e5ff")
        self.response_view.pack(fill=tk.X)

        # --- Audit Trail ---
        audit = ttk.LabelFrame(main, text="运行日志 (Runtime Log)", padding=5)
        audit.pack(fill=tk.BOTH, expand=True, pady=5)
        self.console = scrolledtext.ScrolledText(audit, font=("Consolas", 10), bg="#181818", fg="#00ff00")
        self.console.pack(fill=tk.BOTH, expand=True)

    def sync_scope(self):
        self.core.state = self.core.load_state()
        wp = self.core.state.get("work_path", self.core.root)
        self.scope_label.config(text=f"当前工作路径: {wp}")
        self.log(f"Scope Synced: {wp}")

    def refresh_skills(self):
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        tools = [f[:-3] for f in os.listdir(scripts_dir) if f.endswith(".py") and f not in ["WinyunqBase.py", "RunSkill.py", "SkillGUI.py", "WinyunqCommenter.py", "WinyunqLinter.py"]]
        self.tool_combo['values'] = sorted(tools)
        self.sync_scope()

    def on_tool_selected(self, event):
        tool = self.tool_var.get()
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{tool}.py")
        try:
            output = subprocess.check_output([sys.executable, script_path, "--manifest"], text=True, encoding='utf-8')
            manifest = json.loads(output)
            self.manifest_cache[tool] = manifest
            self.action_combo['values'] = sorted(list(manifest.keys()))
            if self.action_combo['values']: self.action_combo.current(0); self.on_action_selected(None)
        except Exception as e:
            self.log(f"Manifest failed: {e}")

    def on_action_selected(self, event):
        for widget in self.param_entries_frame.winfo_children(): widget.destroy()
        self.param_inputs = {}
        tool = self.tool_var.get()
        action = self.action_var.get()
        info = self.manifest_cache.get(tool, {}).get(action, {})
        
        for p in info.get("params", []):
            name = p["name"]
            row = ttk.Frame(self.param_entries_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{name}:", width=15, anchor="e").pack(side=tk.LEFT, padx=5)
            if name == "content":
                ent = scrolledtext.ScrolledText(row, height=5, font=("Consolas", 10))
            else:
                ent = ttk.Entry(row)
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            self.param_inputs[name] = ent

    def log(self, msg):
        self.console.insert(tk.END, f"> {msg}\n")
        self.console.see(tk.END)

    def execute_mission(self):
        params = {}
        for k, v in self.param_inputs.items():
            if hasattr(v, "get"):
                content = v.get() if not isinstance(v, scrolledtext.ScrolledText) else v.get("1.0", tk.END).strip()
                if content: params[k] = content

        payload = {
            "tool": self.tool_var.get(),
            "winyunqcodestyle": self.style_var.get(),
            "action": self.action_var.get(),
            "params": params
        }
        
        # 更新审计预览
        self.payload_view.delete("1.0", tk.END)
        self.payload_view.insert(tk.END, json.dumps(payload, indent=4, ensure_ascii=False))
        
        with open("WinyunqCoding.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
        
        run_script = os.path.join(os.path.dirname(__file__), "RunSkill.py")
        try:
            res = subprocess.check_output([sys.executable, run_script], text=True, stderr=subprocess.STDOUT, encoding='utf-8')
            self.log("Mission accomplished.")
            
            # 提取 MCP 视野内容并显示
            if "--- MCP OUTPUT ---" in res:
                mcp_data = res.split("--- MCP OUTPUT ---")[1].split("------------------")[0].strip()
                self.response_view.delete("1.0", tk.END)
                self.response_view.insert(tk.END, mcp_data)
        except Exception as e:
            self.log(f"TACTOR FAILED: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SkillGUI(root)
    root.mainloop()
