import tkinter as tk
from tkinter import ttk, messagebox
import os
import shutil
import json

class WinyunqManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Winyunq Agent Skill Manager")
        self.root.geometry("600x450")
        
        # Paths
        self.ProjectSkillPath = os.path.abspath(".agent/skills")
        self.SystemSkillPath = os.path.join(os.environ['USERPROFILE'], ".gemini", "antigravity", "skills")
        
        self.SetupUi()

    def SetupUi(self):
        # Header
        Header = tk.Label(self.root, text="Winyunq Manager", font=("Arial", 18, "bold"))
        Header.pack(pady=10)
        
        # Tabs
        self.TabControl = ttk.Notebook(self.root)
        
        # Tab 1: Installer
        self.InstallTab = ttk.Frame(self.TabControl)
        self.TabControl.add(self.InstallTab, text="Skill Installer")
        self.SetupInstallTab()
        
        # Tab 2: Code Explorer (Locking Status)
        self.StatsTab = ttk.Frame(self.TabControl)
        self.TabControl.add(self.StatsTab, text="Project Status")
        self.SetupStatsTab()
        
        self.TabControl.pack(expand=1, fill="both")

    def SetupInstallTab(self):
        tk.Label(self.InstallTab, text=f"Project Path: {self.ProjectSkillPath}", wraplength=500).pack(pady=5)
        tk.Label(self.InstallTab, text=f"System Path: {self.SystemSkillPath}", wraplength=500).pack(pady=5)
        
        self.InstallBtn = tk.Button(self.InstallTab, text="Install/Sync to Global Space", command=self.SyncSkills, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.InstallBtn.pack(pady=20)

    def SetupStatsTab(self):
        self.RefreshBtn = tk.Button(self.StatsTab, text="Scan Project for Locking Status", command=self.ScanProject)
        self.RefreshBtn.pack(pady=10)
        
        self.StatusArea = tk.Text(self.StatsTab, height=15, width=70)
        self.StatusArea.pack(pady=5)

    def SyncSkills(self):
        try:
            if not os.path.exists(self.SystemSkillPath):
                os.makedirs(self.SystemSkillPath)
            
            for item in os.listdir(self.ProjectSkillPath):
                s = os.path.join(self.ProjectSkillPath, item)
                d = os.path.join(self.SystemSkillPath, item)
                if os.path.isdir(s):
                    if os.path.exists(d): shutil.rmtree(d)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
            
            messagebox.showinfo("Success", "Skills synced to global system space!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def ScanProject(self):
        self.StatusArea.delete('1.0', tk.END)
        self.StatusArea.insert(tk.END, "Scanning src/ for Winyunq (Locked) blocks...\n")
        
        SrcDir = "src"
        if not os.path.exists(SrcDir):
            self.StatusArea.insert(tk.END, "Error: src directory not found.\n")
            return
            
        LockedCount = 0
        fileCount = 0
        
        for root, dirs, files in os.walk(SrcDir):
            for file in files:
                if file.endswith((".cpp", ".hpp", ".py")):
                    fileCount += 1
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Simple check for formal block comments
                        if "/**" in content or "##" in content:
                            LockedCount += 1
                            self.StatusArea.insert(tk.END, f"[LOCKED] {file}\n")
                        else:
                            self.StatusArea.insert(tk.END, f"[OPEN]   {file}\n")
                            
        self.StatusArea.insert(tk.END, f"\n--- Summary ---\nFiles: {fileCount}, Locked: {LockedCount}\n")

if __name__ == "__main__":
    Root = tk.Tk()
    App = WinyunqManagerGUI(Root)
    Root.mainloop()
