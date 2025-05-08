# main_ui.py
import tkinter as tk
import tkinter.font # <-- ***** 添加这一行 *****
from tkinter import filedialog, scrolledtext, ttk, messagebox
import os
import importlib
import traceback
# ... (rest of the imports) ...

# --- Import Helper Modules & Constants ---
try:
    import file_system_utils 
except ImportError:
    # ... (DummyFSUtils) ...
    class DummyFSUtils:
        def get_tree_nodes_for_ui(self, path, **kwargs): return [{"text": f"Error: FS Utils missing", "type": "error", "path": path, "id": path+"_err"}]
        def read_file_content(self, file_path): return f"Content of {os.path.basename(file_path)} (dummy)", None
        def find_relevant_files(self, root_path, **kwargs): return [os.path.join(root_path, "dummy.h")]
    print("WARN: file_system_utils.py not found.")
    file_system_utils = DummyFSUtils()

try:
    import winyunq_formatter
    # Get status constants (MUST exist in formatter)
    STATUS_UNMODIFIED = winyunq_formatter.STATUS_UNMODIFIED
    STATUS_MODIFIED = winyunq_formatter.STATUS_MODIFIED
    STATUS_ERROR = winyunq_formatter.STATUS_ERROR
    STATUS_INFO = winyunq_formatter.STATUS_INFO
    STATUS_BOUNDARY = winyunq_formatter.STATUS_BOUNDARY
    STATUS_RENDERED = getattr(winyunq_formatter,'STATUS_RENDERED', 'rendered') # Allow missing
    STATUS_DEBUG = getattr(winyunq_formatter,'STATUS_DEBUG', 'debug')         # Allow missing
except ImportError:
    # Define dummy formatter and constants
    class DummyFormatter:
        STATUS_UNMODIFIED="unmodified"; STATUS_MODIFIED="modified"; STATUS_ERROR="error"; STATUS_INFO="info"; STATUS_BOUNDARY="boundary"; STATUS_RENDERED="rendered"; STATUS_DEBUG="debug"
        def process_code(self, code_string, config=None):
             phase = config.get("target_phase", 1) if config else 1
             print(f"DummyFormatter: process_code(Phase {phase}) -> Returning lines with status")
             lines_data = []
             if phase == 3: # Special case for debug string
                 lines_data = [{"text": f"-- Dummy Debug Output (Phase 3) --\n{code_string}", "status": self.STATUS_DEBUG, "orig_line": 0}]
             else: # Default lines with status
                 for i, line in enumerate(code_string.splitlines()):
                     status = self.STATUS_MODIFIED if i % 3 == 1 else (self.STATUS_ERROR if i%3 == 2 else self.STATUS_UNMODIFIED)
                     if "/**" in line or "**/" in line: status = self.STATUS_BOUNDARY
                     lines_data.append({"text": line + f" (dummy_p{phase})", "status": status, "orig_line": i})
             return {"success": True, "error_message": None, "lines": lines_data, "summary": {}} # Removed output_type
    print("WARN: winyunq_formatter.py not found.")
    winyunq_formatter = DummyFormatter()
    STATUS_UNMODIFIED = DummyFormatter.STATUS_UNMODIFIED; STATUS_MODIFIED = DummyFormatter.STATUS_MODIFIED; STATUS_ERROR = DummyFormatter.STATUS_ERROR; STATUS_INFO = DummyFormatter.STATUS_INFO; STATUS_BOUNDARY = DummyFormatter.STATUS_BOUNDARY; STATUS_RENDERED=DummyFormatter.STATUS_RENDERED; STATUS_DEBUG=DummyFormatter.STATUS_DEBUG

# --- Main Application Class ---
class WinyunqDocStylerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WinyunqDoc Styler (v1.1 - Color Feedback)")
        self.root.geometry("1200x800")
        script_dir = os.path.abspath(os.path.dirname(__file__))
        self.current_path = tk.StringVar(value=script_dir)
        self.selected_file_path = None

        # --- Style Tags (Defined once based on imported/dummy constants) ---
        self.text_tags = {
            STATUS_UNMODIFIED: {"foreground": "#008000"},
            STATUS_MODIFIED: {"foreground": "#0000FF", "font": ("Consolas", 9, "bold") if "Consolas" in tk.font.families() else "TkDefaultFont 9 bold"},
            STATUS_ERROR: {"foreground": "#FF0000", "background": "#FFEEEE"},
            STATUS_INFO: {"foreground": "gray"},
            STATUS_BOUNDARY: {"font": ("Consolas", 9, "bold") if "Consolas" in tk.font.families() else "TkDefaultFont 9 bold"},
            STATUS_RENDERED: {}, # Use default text color
            STATUS_DEBUG: {"foreground": "#444444", "font": "TkFixedFont"},
            None: {} # Default style for lines with status=None
        }

        # --- Config for Formatter ---
        self.formatter_config = {"target_phase": 1} # Default phase

        # --- Setup UI ---
        self._setup_ui()
        self._configure_tags()
        self._load_initial_directory()

    def _setup_ui(self):
        # Top Frame
        self.top_frame = ttk.Frame(self.root, padding="10")
        self.top_frame.pack(side=tk.TOP, fill=tk.X)
        self.browse_button = ttk.Button(self.top_frame, text="Browse...", command=self.ui_action_browse)
        self.browse_button.pack(side=tk.LEFT, padx=(0,10))
        self.path_display = ttk.Label(self.top_frame, textvariable=self.current_path, relief=tk.SUNKEN, padding=2, anchor='w')
        self.path_display.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Controls Frame
        self.controls_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        self.controls_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(self.controls_frame, text="Mode:").pack(side=tk.LEFT, padx=(0,5))
        self.phase_options = { "Phase 1: Prefixes": 1, "Phase 2: T1 Indent": 2, "Phase 3: T2 Align": 3, "Phase 4: Render": 4, "DEBUG: Show Tree": 99 }
        self.phase_combo_var = tk.StringVar(value=list(self.phase_options.keys())[0]) # Default Phase 1
        self.phase_combo = ttk.Combobox(self.controls_frame, textvariable=self.phase_combo_var,
                                        values=list(self.phase_options.keys()), width=18, state="readonly")
        self.phase_combo.pack(side=tk.LEFT, padx=5)
        self.phase_combo.bind('<<ComboboxSelected>>', self.ui_update_config)
        self.ui_update_config() # Set initial

        self.process_button = ttk.Button(self.controls_frame, text="Process/Show", command=self.ui_action_process_selected, state=tk.DISABLED)
        self.process_button.pack(side=tk.LEFT, padx=10)
        self.reload_button = ttk.Button(self.controls_frame, text="Reload Fmt", command=self.ui_action_reload)
        self.reload_button.pack(side=tk.LEFT, padx=5)

        # Main Paned Window
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL) # Removed sashrelief
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        # Left: File Tree
        self.tree_frame = ttk.Frame(self.paned_window, width=400)
        self.paned_window.add(self.tree_frame, weight=1)
        self.tree = ttk.Treeview(self.tree_frame, selectmode="browse", show="tree")
        # ... (Scrollbars setup) ...
        self.tree_scrollbar_y = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree_scrollbar_x = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.tree_scrollbar_y.set, xscrollcommand=self.tree_scrollbar_x.set)
        self.tree_scrollbar_y.pack(side=tk.RIGHT, fill="y")
        self.tree_scrollbar_x.pack(side=tk.BOTTOM, fill="x")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.ui_event_item_selected)
        self.tree.bind("<<TreeviewOpen>>", self.ui_event_node_expand)

        # Middle: Original Preview
        self.original_text_frame = ttk.Frame(self.paned_window, width=400)
        self.paned_window.add(self.original_text_frame, weight=2)
        ttk.Label(self.original_text_frame, text="Original Preview:").pack(anchor=tk.NW, padx=5, pady=5)
        self.original_text_area = scrolledtext.ScrolledText(self.original_text_frame, wrap=tk.NONE, undo=False, state=tk.DISABLED)
        self.original_text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))

        # Right: Formatter Output
        self.styled_text_frame = ttk.Frame(self.paned_window, width=450)
        self.paned_window.add(self.styled_text_frame, weight=2)
        ttk.Label(self.styled_text_frame, text="Formatter Output (Colors: Green=OK, Blue=Mod, Red=Err):").pack(anchor=tk.NW, padx=5, pady=5)
        self.styled_text_area = scrolledtext.ScrolledText(self.styled_text_frame, wrap=tk.NONE, state=tk.DISABLED)
        self.styled_text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))


# main_ui.py (Focus on _display_formatter_result_with_status in v1.1)

# ... (Imports and other parts of the class remain) ...

    def _configure_tags(self):
        """Configures tags for the styled text area."""
        print("Configuring tags...") # Debug print
        self.styled_text_area.config(state=tk.NORMAL)
        for tag_name, config in self.text_tags.items():
            if tag_name is not None:
                 print(f"  Configuring tag: {tag_name} with {config}") # Debug print
                 try:
                     self.styled_text_area.tag_configure(tag_name, **config)
                 except tk.TclError as e:
                      print(f"    Warning: Could not configure tag '{tag_name}': {e}") # Warn if config fails
        # Ensure boundary tag exists and is configured
        boundary_config = self.text_tags.get(STATUS_BOUNDARY, {"font": "TkDefaultFont 9 bold"}) # Get config or default
        print(f"  Ensuring boundary tag: {STATUS_BOUNDARY} with {boundary_config}")
        self.styled_text_area.tag_configure(STATUS_BOUNDARY, **boundary_config)
        self.styled_text_area.config(state=tk.DISABLED)


    def _display_formatter_result_with_status(self, result):
        """Displays the structured result, applying tags based on line status."""
        self.styled_text_area.config(state=tk.NORMAL)
        self.styled_text_area.delete('1.0', tk.END)
        print("--- Displaying Formatter Result ---") # Debug print

        # Clear existing style tags FIRST
        # print("Removing existing tags:", self.styled_text_area.tag_names()) # Debug
        for tag_name in self.text_tags: # Use keys from our definition
            if tag_name is not None:
                 try:
                     self.styled_text_area.tag_remove(tag_name, "1.0", tk.END)
                 except tk.TclError: pass # Ignore if tag doesn't exist yet
        # Explicitly remove boundary tag as well, as it might be applied based on content later
        try:
            self.styled_text_area.tag_remove(STATUS_BOUNDARY, "1.0", tk.END)
        except tk.TclError: pass


        if not result or not result.get("success", False):
            error_msg = result.get("error_message", "Formatter returned unsuccessful or invalid result.")
            print(f"Formatter failed: {error_msg}") # Debug print
            self.styled_text_area.insert('1.0', f"Formatting Failed:\n\n{error_msg}")
            self.styled_text_area.tag_add(STATUS_ERROR, "1.0", tk.END) # Apply error tag
        else:
            lines_data = result.get("lines", [])
            print(f"Received {len(lines_data)} lines from formatter.") # Debug print
            if not lines_data:
                 self.styled_text_area.insert('1.0', "(Formatter returned no lines)")
            else:
                 # --- Process lines and apply tags ---
                 current_line_start_index = "1.0" # Tkinter index for start of current line
                 for line_info in lines_data:
                     text = line_info.get("text", "")
                     status = line_info.get("status") # Status string from formatter
                     # orig_line = line_info.get("orig_line", -1) # Get original line number if needed

                     line_end_index = self.styled_text_area.index(f"{current_line_start_index} + {len(text)} chars")
                     
                     # Insert text for the current line FIRST
                     self.styled_text_area.insert(current_line_start_index, text + "\n")
                     
                     # Define the range for applying the tag (excluding the newline)
                     tag_start_index = current_line_start_index
                     tag_end_index = self.styled_text_area.index(f"{tag_start_index} + {len(text)} chars") # End before newline

                     # Debug print for each line
                     # print(f"  Line {int(current_line_start_index.split('.')[0])}: Status='{status}', Range='{tag_start_index}' to '{tag_end_index}', Text='{text[:20]}...'")

                     # Apply tag based on status
                     if status and status in self.text_tags:
                         # print(f"    Applying tag: {status}") # Debug
                         self.styled_text_area.tag_add(status, tag_start_index, tag_end_index)
                     elif status and status not in self.text_tags:
                          print(f"    Warning: Unknown status '{status}' received from formatter.")

                     # Apply boundary tag specifically based on content or status
                     if status == STATUS_BOUNDARY or text.strip() in ("/**", "**/"):
                          # print(f"    Applying boundary tag.") # Debug
                          self.styled_text_area.tag_add(STATUS_BOUNDARY, tag_start_index, tag_end_index)
                          # If boundary status was UNMODIFIED but we want bold, ensure bold tag is applied
                          # This depends if STATUS_BOUNDARY itself implies bold in self.text_tags

                     # Move to the start of the next line
                     current_line_start_index = self.styled_text_area.index(f"{tag_end_index} + 1 char") # Move past the newline

        self.styled_text_area.config(state=tk.DISABLED)
        print("--- Finished Displaying Result ---") # Debug print

    # --- UI Update Functions ---
    def _load_initial_directory(self):
        # ... (calls ui_update_file_tree) ...
        initial_path = self.current_path.get()
        if os.path.isdir(initial_path):
            self.ui_update_file_tree(initial_path)

    def _clear_displays(self):
        # ... (calls _display_text_in_widget) ...
        self._display_text_in_widget(self.original_text_area, "")
        self._display_text_in_widget(self.styled_text_area, "")
        self.process_button.config(state=tk.DISABLED)
        self.selected_file_path = None

    def _display_text_in_widget(self, widget, text, state=tk.DISABLED):
        # ... (same as v0.9) ...
        widget.config(state=tk.NORMAL)
        widget.delete('1.0', tk.END)
        if text: widget.insert('1.0', text)
        widget.config(state=state)

    def _handle_error(self, message, exception_obj=None):
        # ... (same as v0.9) ...
        print(f"ERROR: {message}")
        full_message = message
        if exception_obj:
            print(traceback.format_exc())
            full_message += f"\n\nDetails:\n{traceback.format_exc(limit=1)}"
        messagebox.showerror("Error", full_message)
        # Display error in styled area
        self._display_text_in_widget(self.styled_text_area, f"Error:\n{message}", state=tk.DISABLED)
        # Maybe apply error tag?
        self.styled_text_area.config(state=tk.NORMAL)
        self.styled_text_area.tag_add(STATUS_ERROR, "1.0", tk.END)
        self.styled_text_area.config(state=tk.DISABLED)


    def _display_formatter_result_with_status(self, result):
        """Displays the structured result, applying tags based on line status."""
        self.styled_text_area.config(state=tk.NORMAL)
        self.styled_text_area.delete('1.0', tk.END)

        # Clear style tags
        for tag_name in self.text_tags:
            if tag_name is not None: self.styled_text_area.tag_remove(tag_name, "1.0", tk.END)
        self.styled_text_area.tag_remove(STATUS_BOUNDARY, "1.0", tk.END) # Ensure boundary cleared

        if not result or not result.get("success", False):
            error_msg = result.get("error_message", "Formatter returned unsuccessful or invalid result.")
            self.styled_text_area.insert('1.0', f"Formatting Failed:\n\n{error_msg}")
            self.styled_text_area.tag_add(STATUS_ERROR, "1.0", tk.END) # Apply error tag
        else:
            lines_data = result.get("lines", [])
            if not lines_data:
                 self.styled_text_area.insert('1.0', "(Formatter returned no lines)")
            else:
                 # Check if it's a single debug/rendered string disguised as lines_data
                 if len(lines_data) == 1 and lines_data[0].get("status") in [STATUS_DEBUG, STATUS_RENDERED]:
                      full_text = lines_data[0].get("text","") + "\n"
                      status_tag = lines_data[0].get("status")
                      self.styled_text_area.insert('1.0', full_text)
                      if status_tag in self.text_tags: # Apply overall tag
                           self.styled_text_area.tag_add(status_tag, "1.0", tk.END)
                      # Apply boundary tags if rendered output
                      if status_tag == STATUS_RENDERED: self.apply_basic_boundary_tags(self.styled_text_area)
                 else: # Assume it's lines_with_status
                    line_num = 1
                    for line_info in lines_data:
                        text = line_info.get("text", "")
                        status = line_info.get("status") # Status string from formatter
                        start = f"{line_num}.0"
                        self.styled_text_area.insert(tk.END, text + "\n")
                        end = f"{line_num}.{len(text)}"
                        if status and status in self.text_tags: # Check if status is known
                            self.styled_text_area.tag_add(status, start, end)
                        # Apply boundary tag based on status OR content
                        if status == STATUS_BOUNDARY or text.strip() in ("/**", "**/"):
                             self.styled_text_area.tag_add(STATUS_BOUNDARY, start, end)
                        line_num += 1

        self.styled_text_area.config(state=tk.DISABLED)

    # --- UI Action Handlers ---

    def ui_action_browse(self):
        # ... (same as v0.9) ...
        directory = filedialog.askdirectory(initialdir=self.current_path.get() or os.getcwd())
        if directory:
            abs_dir = os.path.abspath(directory); self.current_path.set(abs_dir)
            self._clear_displays(); self.ui_update_file_tree(abs_dir)

    def ui_update_file_tree(self, directory_path):
        # ... (same as v0.9 - calls get_tree_nodes_for_ui) ...
        for i in self.tree.get_children(): self.tree.delete(i)
        try:
            nodes_data = file_system_utils.get_tree_nodes_for_ui(directory_path, max_depth=1)
            self._insert_tree_nodes_from_data("", nodes_data)
        except Exception as e: self._handle_error(f"Populate tree failed", e)

    def _insert_tree_nodes_from_data(self, parent_id, nodes_data):
        # ... (same as v0.9) ...
         for node_info in nodes_data:
            node_id = self.tree.insert(parent_id, "end", iid=node_info.get('id'), text=node_info.get('text'), values=(node_info.get('type'), node_info.get('path')), open=False)
            if node_info.get('type') == 'folder' and node_info.get('has_children'): self.tree.insert(node_id, "end", text="...") 

    def ui_event_item_selected(self, event=None):
        # ... (same as v0.9 - calls read_file_content) ...
        selected_id = self.tree.focus(); self._clear_displays()
        if not selected_id: return
        item = self.tree.item(selected_id); item_values = item.get("values")
        if not item_values or len(item_values) < 2: return
        item_type, item_path = item_values
        if item_type == "file":
            self.selected_file_path = item_path
            try:
                content, error = file_system_utils.read_file_content(item_path)
                self._display_text_in_widget(self.original_text_area, content if not error else f"Error:\n{error}")
                self.process_button.config(state=tk.NORMAL if not error else tk.DISABLED)
            except Exception as e: self._handle_error(f"Read file failed: {item_path}", e); self.process_button.config(state=tk.DISABLED)
        else: self.selected_file_path = None; self.process_button.config(state=tk.DISABLED); self._display_text_in_widget(self.original_text_area, f"{item_type.capitalize()} selected.")

    def ui_event_node_expand(self, event=None):
        # ... (same as v0.9 - calls get_tree_nodes_for_ui) ...
        node_id = self.tree.focus(); item = self.tree.item(node_id); item_values = item.get("values")
        if not item_values or len(item_values) < 2 or item_values[0] != "folder": return
        children = self.tree.get_children(node_id)
        if children and self.tree.item(children[0], "text") == "...":
            folder_path = item_values[1]
            try:
                children_data = file_system_utils.get_tree_nodes_for_ui(folder_path, node_id=node_id)
                for child in children: self.tree.delete(child)
                self._insert_tree_nodes_from_data(node_id, children_data)
            except Exception as e: self._handle_error(f"Expand folder failed: {folder_path}", e)

    def ui_update_config(self, event=None):
        # ... (same as v0.9) ...
        selected_display_text = self.phase_combo_var.get()
        selected_phase_value = self.phase_options.get(selected_display_text, 4)
        self.formatter_config["target_phase"] = selected_phase_value


    def ui_action_process_selected(self):
        """Action for the 'Process/Show' button."""
        if not self.selected_file_path: return messagebox.showwarning("No File", "Select file.")
        try:
            original_content, error = file_system_utils.read_file_content(self.selected_file_path)
            if error: return self._handle_error(f"Cannot format: {error}")
            original_content = original_content or ""
            config = self.formatter_config
            print(f"UI: Calling process_code with config: {config}")
            # --- Interface Call ---
            result = winyunq_formatter.process_code(original_content, config=config) # Expects dict
            # --- Display Result ---
            self._display_formatter_result_with_status(result) # Use the dedicated display function
        except Exception as e: self._handle_error("Formatting Error", e)


    def ui_action_reload(self):
        # ... (same as v0.9) ...
        global winyunq_formatter, STATUS_MAP 
        try:
            print("Attempting reload...")
            # Need to handle potential errors during reload/import
            if 'winyunq_formatter' in globals() and hasattr(winyunq_formatter, '__file__'):
                 winyunq_formatter = importlib.reload(winyunq_formatter)
            else:
                 import winyunq_formatter
            # Reload constants
            STATUS_MAP = {getattr(winyunq_formatter, k, k.lower()): k.lower() for k in dir(winyunq_formatter) if k.startswith("STATUS_")}
            self._configure_tags() # Reconfigure tags with potentially new status names/styles
            print("Reload successful.")
            messagebox.showinfo("Reload", "Formatter module reloaded.")
        except Exception as e: self._handle_error("Reload Failed", e)

    # --- Progress Bar Helpers & Boundary Tags --- (Keep these UI helpers)
    def _create_progress_window(self, total):
        # ... (implementation) ...
        win = tk.Toplevel(self.root); win.title("Working..."); win.geometry("400x100"); win.resizable(False, False); win.transient(self.root); win.grab_set()
        ttk.Label(win, text="Processing...", padding=5).pack()
        pb = ttk.Progressbar(win, orient="horizontal", length=350, mode="determinate", maximum=total); pb.pack(pady=5)
        lbl = ttk.Label(win, text="Starting...", padding=5, width=50, anchor='w', justify='left'); lbl.pack()
        win.pb = pb; win.status_label = lbl
        return win
        
    def _update_progress(self, win, current, total, name):
        # ... (implementation) ...
        if win.winfo_exists():
            win.pb['value'] = current; max_len = 45; d_name = name if len(name) <= max_len else name[:max_len-3] + "..."
            win.status_label['text'] = f"({current}/{total}): {d_name:.{max_len}s}"; win.update_idletasks() 

    def apply_basic_boundary_tags(self, text_widget):
         # This helper is fine to keep in UI as it applies visual tag based on text content
         start_index = "1.0"
         while True:
             pos = text_widget.search("/**", start_index, stopindex=tk.END, exact=True, regexp=False, nocase=False)
             if not pos: break
             line_start = pos.split('.')[0] + ".0"
             if text_widget.get(line_start, pos).strip() == "": 
                  text_widget.tag_add(STATUS_BOUNDARY, pos, f"{pos}+{len('/**')}c")
             start_index = f"{pos}+{len('/**')}c" 
         start_index = "1.0"
         while True:
             pos = text_widget.search("**/", start_index, stopindex=tk.END, exact=True, regexp=False, nocase=False)
             if not pos: break
             line_start = pos.split('.')[0] + ".0"
             if text_widget.get(line_start, pos).strip() == "":
                  text_widget.tag_add(STATUS_BOUNDARY, pos, f"{pos}+{len('**/')}c")
             start_index = f"{pos}+{len('**/')}c"

# --- Main Execution ---
if __name__ == "__main__":
    app_root = tk.Tk()
    style = ttk.Style(app_root)
    # ... (theme setup) ...
    try: 
        if "clam" in style.theme_names(): style.theme_use("clam")
        elif "vista" in style.theme_names() and os.name == 'nt': style.theme_use("vista")
    except tk.TclError: print("Themes not available.") 
    app = WinyunqDocStylerApp(app_root)
    app_root.mainloop()