# prefix_formatter.py (v1.1 - Fixed /** indent and handles */ end)

# Define status constants
STATUS_UNMODIFIED = "unmodified"
STATUS_MODIFIED = "modified"
STATUS_ERROR = "error"
STATUS_BOUNDARY = "boundary"

def normalize_block_prefixes(block_text):
    """
    PHASE 1/2 PIPELINE STAGE:
    Ensures a Doxygen block starts with '/**' (at column 1),
    ends with '**/' (at column 1, attempting to fix '*/'),
    and all content lines start with ' * ' (star at column 2).

    Args:
        block_text: The string content of a single Doxygen block.

    Returns:
        A list of tuples: (formatted_line_text, status, original_line_number_in_block)
    """
    original_lines = block_text.splitlines()
    processed_lines_info = []
    line_idx = -1

    if not original_lines:
        return []

    # --- 1. Process /** line and FORCE it to column 1 ---
    line_idx += 1
    orig_first_line = original_lines[line_idx]
    status_first = STATUS_UNMODIFIED
    
    # Check content first
    if not orig_first_line.strip().startswith("/**"): # Check if it even contains /**
        status_first = STATUS_ERROR # Mark as error if content doesn't start with /**
        processed_lines_info.append(("/**", status_first, line_idx)) # Output correct /**
    else:
        # Content is okay (starts with /**), now check physical position
        if not orig_first_line.startswith("/**"): # Not at column 1
            status_first = STATUS_MODIFIED # Mark as modified because we will force it
        # Always output the canonical "/**" at column 1
        processed_lines_info.append(("/**", status_first if status_first != STATUS_UNMODIFIED else STATUS_BOUNDARY, line_idx))

    # --- 2. Process content lines ---
    start_content_idx = 1
    end_content_idx = len(original_lines) - 1

    single_line_content_extracted = None
    # Check for single line block /** content **/ or /** content */
    first_line_stripped = orig_first_line.lstrip()
    is_single_line = (len(original_lines) == 1 and 
                      first_line_stripped.startswith("/**") and
                      (orig_first_line.rstrip().endswith("**/") or orig_first_line.rstrip().endswith("*/")))
                      
    if is_single_line and len(first_line_stripped) > len("/**/") : # Ensure there is content
         end_marker_len = 3 if orig_first_line.rstrip().endswith("**/") else 2
         single_line_content_extracted = orig_first_line.lstrip()[len("/**"):len(first_line_stripped)-end_marker_len].strip()
         end_content_idx = 0 
         start_content_idx = 1 

    for idx_orig_line in range(start_content_idx, end_content_idx):
        line_idx += 1
        orig_content_line = original_lines[idx_orig_line]
        status_content = STATUS_UNMODIFIED
        formatted_content_line = ""
        stripped_line = orig_content_line.lstrip()
        target_prefix = " * " 
        markdown_part = ""

        if stripped_line.startswith("* "): 
            markdown_part = stripped_line[2:]
            # Force prefix " * " starting at col 1 (star at col 2)
            formatted_content_line = target_prefix + markdown_part
            if not orig_content_line.startswith(" * "): status_content = STATUS_MODIFIED
        elif stripped_line.startswith("*"): 
            status_content = STATUS_MODIFIED
            if len(stripped_line) == 1: 
                target_prefix = " *" # Empty line format
                markdown_part = ""
            else: 
                markdown_part = stripped_line[1:]
            formatted_content_line = target_prefix + markdown_part
        elif stripped_line == "": 
            target_prefix = " *"
            markdown_part = ""
            formatted_content_line = target_prefix + markdown_part
            if orig_content_line.strip() != "*": # Check if original was truly just spaces or empty
                status_content = STATUS_MODIFIED # Only modified if original wasn't already effectively " *"
        else: 
            status_content = STATUS_MODIFIED
            markdown_part = stripped_line
            formatted_content_line = target_prefix + markdown_part

        processed_lines_info.append((formatted_content_line, status_content, line_idx))
        
    if single_line_content_extracted is not None:
         line_idx += 1
         processed_lines_info.append((" * " + single_line_content_extracted, STATUS_MODIFIED, 0)) 

    # --- 3. Process **/ line and FORCE it to column 1, fixing */ ---
    if len(original_lines) == 1 and single_line_content_extracted is None and stripped_first == "/**":
        # Handle input of just "/**"
        line_idx += 1
        processed_lines_info.append(("**/", STATUS_MODIFIED, line_idx))
    elif len(original_lines) > 1 or single_line_content_extracted is not None:
        original_last_line_idx = len(original_lines) - 1
        # Use the correct original line index
        line_idx = original_last_line_idx if single_line_content_extracted is None else 1 # Index 1 for synthetic last line of single-line block

        orig_last_line = original_lines[original_last_line_idx]
        status_last = STATUS_UNMODIFIED
        
        stripped_last = orig_last_line.strip()
        
        # Check if it ends correctly with **/ or incorrectly with */
        is_correct_end = stripped_last == "**/"
        is_fixable_end = stripped_last == "*/" # Check for incorrect ending

        if is_correct_end:
            if not orig_last_line.startswith("**/"): # Correct content, wrong position
                status_last = STATUS_MODIFIED
        elif is_fixable_end: # Incorrect content */
            status_last = STATUS_MODIFIED # Mark modified because we fix */ to **/
            if not orig_last_line.startswith("*/"): # Also wrong position
                pass # Status is already modified
        else: # Content is not **/ or */
            status_last = STATUS_ERROR # Mark as error

        # Always output the canonical "**/" at column 1
        processed_lines_info.append(("**/", status_last if status_last != STATUS_UNMODIFIED else STATUS_BOUNDARY, line_idx))

    return processed_lines_info