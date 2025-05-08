# file_system_utils.py
import os

def get_tree_nodes_for_ui(path, node_id=None, max_depth=1, current_depth=0, filters=None):
    """
    Gets directory structure suitable for UI Treeview insertion for one level.
    Returns list of node dictionaries: {'id': unique_id, 'text': 'display', 'type': 'folder'/'file'/'error', 'path': full_path, 'has_children': bool}.
    """
    if filters is None: filters = [".h", ".cpp", ".hpp", ".c", ".txt"]
    nodes = []
    try:
        # Sort items: folders first, then files
        items = sorted(os.listdir(path), key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
        for name in items:
            full_path = os.path.join(path, name)
            node = {"name": name, "path": full_path, "id": full_path} # Use path as default ID
            try:
                if os.path.isdir(full_path):
                    node["type"] = "folder"
                    node["text"] = f"📁 {name}"
                    # Check if it has children (only if needed for placeholder)
                    try:
                        node["has_children"] = bool(os.listdir(full_path))
                    except OSError: # Permission error listing children
                        node["has_children"] = False
                        node["text"] += " [X]" # Indicate access issue
                    nodes.append(node)
                elif os.path.isfile(full_path):
                    if not filters or any(name.endswith(ext) for ext in filters):
                        node["type"] = "file"
                        node["text"] = f"📄 {name}"
                        node["has_children"] = False
                        nodes.append(node)
            except OSError: continue # Skip item on stat error
    except OSError as e:
        nodes.append({"text": f"🚫 Error: {e.strerror}", "type": "error", "path": path, "id": path+"_error"})
    return nodes


def read_file_content(file_path):
    """Reads file content, returns (content_string, error_string)."""
    encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
    last_error = "Unknown read error."
    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f: return f.read(), None
        except (UnicodeDecodeError, LookupError) as e: last_error = f"Decode Error ('{enc}'): {e}"
        except Exception as e: return None, f"Read Error: {e}"
    return None, f"Failed decodings. Last: {last_error}"

def find_relevant_files(root_path, extensions=None):
    """Finds relevant files recursively."""
    if extensions is None: extensions = [".h", ".cpp", ".hpp", ".c"]
    relevant_files = []
    for root_dir, _, files in os.walk(root_path):
        for file_name in files:
            if any(file_name.endswith(ext) for ext in extensions):
                try: # Ensure path is valid before adding
                    full_path = os.path.join(root_dir, file_name)
                    if os.path.exists(full_path): # Basic check
                         relevant_files.append(full_path)
                except Exception as e:
                     print(f"Warning: Skipping file due to path issue: {e}")
                     continue
    return relevant_files