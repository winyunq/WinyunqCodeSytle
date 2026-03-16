import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import sys
import difflib
import os

class DiffGUI:
    def __init__(self, filename, old_content, new_content):
        self.root = tk.Tk()
        self.root.title(f"Winyunq Security Alert: {filename}")
        self.root.geometry("1000x600")
        
        self.result = False
        
        # Header
        header = ttk.Label(self.root, text=f"File '{filename}' is LOCKED.\nAn edit is attempting to modify protected content. Review the changes below:", font=("Arial", 11, "bold"))
        header.pack(pady=10)
        
        # Diff Area
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10)
        
        # Left: Original
        f1 = ttk.LabelFrame(paned, text="Original Content")
        paned.add(f1, weight=1)
        self.txt_old = scrolledtext.ScrolledText(f1, font=("Consolas", 10))
        self.txt_old.pack(fill=tk.BOTH, expand=True)
        self.txt_old.insert(tk.END, old_content)
        self.txt_old.config(state="disabled")
        
        # Right: New
        f2 = ttk.LabelFrame(paned, text="Proposed Change")
        paned.add(f2, weight=1)
        self.txt_new = scrolledtext.ScrolledText(f2, font=("Consolas", 10))
        self.txt_new.pack(fill=tk.BOTH, expand=True)
        self.txt_new.insert(tk.END, new_content)
        
        # Highlight Differences (Simple)
        self.highlight_diff(old_content, new_content)

        # Actions
        btn_frame = ttk.Frame(self.root, padding="10")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(btn_frame, text="CANCEL (Reject Edit)", command=self.on_cancel).pack(side=tk.LEFT, padx=20)
        ttk.Button(btn_frame, text="FORCE UNLOCK & APPLY (Allow Edit)", command=self.on_confirm).pack(side=tk.RIGHT, padx=20)

        self.root.protocol("WM_DELETE_WINDOW", self.on_cancel)

    def highlight_diff(self, a, b):
        # A very basic tag highlighter could go here
        # For now, relying on side-by-side view
        pass

    def on_confirm(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to force overwrite this locked file?"):
            self.result = True
            self.root.destroy()

    def on_cancel(self):
        self.result = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.result

def show_diff_dialog(file_path, new_content):
    if not os.path.exists(file_path):
        old_content = "(New File)"
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            old_content = f.read()
            
    app = DiffGUI(os.path.basename(file_path), old_content, new_content)
    return app.run()

if __name__ == "__main__":
    # Test Mode
    # python UnlockGUI.py raw_file new_file
    if len(sys.argv) > 2:
        with open(sys.argv[1], 'r') as f: o = f.read()
        with open(sys.argv[2], 'r') as f: n = f.read()
        app = DiffGUI("Test", o, n)
        app.run()
