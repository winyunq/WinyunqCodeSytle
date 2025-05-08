# block_extractor.py 
import re

STATUS_UNMODIFIED = "unmodified"
STATUS_MODIFIED = "modified"
STATUS_ERROR = "error"
STATUS_BOUNDARY = "boundary" 

def extract_and_normalize_boundaries(code_string):
    """
    Pipeline Stage 1: Extracts Doxygen blocks, normalizes/forces 
    /** and **/ boundaries to be at column 1, and marks boundary status.
    Content lines status set to UNMODIFIED initially.

    Returns: list[dict]: 
        {'processed_lines': list[tuple(text, status)], 'start_line_orig': int, ...}
    """
    # ... (在这里实现我们上一轮讨论的、正确的 extract_and_normalize_boundaries 逻辑) ...
    # ... 这个函数现在只在这里实现一次 ...
    processed_blocks_info = []
    lines_original = code_string.splitlines()
    # ... (查找、处理、状态标记逻辑 - 从上个回复复制过来) ...
    current_pos = 0
    line_start_positions = [0]
    for i, line in enumerate(lines_original):
        current_pos += len(line) + (1 if i < len(lines_original) - 1 else 0)
        line_start_positions.append(current_pos)

    def get_line_index(char_index):
        for i in range(len(line_start_positions) - 1):
            if line_start_positions[i] <= char_index < line_start_positions[i+1]: return i
        if char_index >= line_start_positions[-1]: return len(lines_original) - 1
        return len(lines_original) - 1

    potential_block_starts = []
    for i, line in enumerate(lines_original):
        match = re.search(r"/\*\*", line)
        if match:
            stripped_line = line.lstrip()
            if stripped_line.startswith("/**") and not stripped_line.startswith("/***/"):
                start_offset_in_line = match.start()
                start_char_index = line_start_positions[i] + start_offset_in_line
                starts_at_col_0 = (start_offset_in_line == 0)
                potential_block_starts.append({ "start_marker": "/**", "start_index": start_char_index, "start_line": i, "start_col0": starts_at_col_0, "start_line_text": line })

    potential_block_starts.sort(key=lambda x: x["start_index"])
    processed_spans = set()
    processed_char_end = 0

    for start_info in potential_block_starts:
        start_index = start_info["start_index"]; start_line_idx = start_info["start_line"]
        start_col0 = start_info["start_col0"]; start_line_text = start_info["start_line_text"] 

        if start_line_idx in processed_spans or start_index < processed_char_end: continue

        search_start = start_index + 3
        end_match_double = re.search(r"\*\*/", code_string[search_start:])
        end_match_single = re.search(r"\*/", code_string[search_start:])
        chosen_end_match = None; is_single_star_end = False
        if end_match_double and end_match_single:
            chosen_end_match = end_match_double if end_match_double.start() <= end_match_single.start() else end_match_single
            is_single_star_end = (chosen_end_match == end_match_single) and (end_match_double.start() > end_match_single.start() if end_match_double else True)
        elif end_match_double: chosen_end_match = end_match_double
        elif end_match_single: chosen_end_match = end_match_single; is_single_star_end = True
            
        if chosen_end_match:
            end_index_relative = chosen_end_match.end()
            end_index_absolute = search_start + end_index_relative
            end_line_idx = get_line_index(end_index_absolute - 1)

            current_block_span = range(start_line_idx, end_line_idx + 1)
            if any(i in processed_spans for i in current_block_span): continue

            processed_lines = []
            
            # Start Line
            status_start = STATUS_BOUNDARY
            if start_line_text.strip() != "/**": status_start = STATUS_ERROR
            elif not start_col0: status_start = STATUS_MODIFIED
            processed_lines.append(("/**", status_start))

            # Middle Lines
            for i in range(start_line_idx + 1, end_line_idx):
                 if i < len(lines_original): 
                    # --- START MODIFICATION ---
                    orig_content_line = lines_original[i]
                    status_content = STATUS_UNMODIFIED # Assume GREEN
                    normalized_line = ""
                    stripped_line = orig_content_line.lstrip()
                    target_prefix = " * "
                    markdown_part = ""

                    # Determine normalized form and if modification occurred
                    if stripped_line.startswith("* "): 
                        markdown_part = stripped_line[2:]
                        normalized_line = target_prefix + markdown_part
                        # Check original physical prefix
                        if not orig_content_line.startswith(" * "): 
                            status_content = STATUS_MODIFIED # BLUE
                    elif stripped_line.startswith("*"): 
                        status_content = STATUS_MODIFIED # BLUE
                        target_prefix = " *" if len(stripped_line) == 1 else " * "
                        markdown_part = "" if len(stripped_line) == 1 else stripped_line[1:]
                        normalized_line = target_prefix + markdown_part
                    elif stripped_line == "": 
                        target_prefix = " *"
                        markdown_part = ""
                        normalized_line = target_prefix + markdown_part
                        if orig_content_line.strip() != "*" and orig_content_line.strip() != "": 
                             status_content = STATUS_MODIFIED # BLUE
                        elif orig_content_line != " *": # If original was "*" or just spaces
                             status_content = STATUS_MODIFIED # BLUE
                    else: # Missing '*' prefix
                        status_content = STATUS_MODIFIED # BLUE
                        markdown_part = stripped_line
                        normalized_line = target_prefix + markdown_part
                    
                    processed_lines.append((normalized_line, status_content)) 
                    # --- END MODIFICATION ---
                 # else: line index out of bounds? Should not happen if end_line_idx is correct
                 
            # End Line
            if end_line_idx >= start_line_idx and end_line_idx < len(lines_original):
                 end_line_text = lines_original[end_line_idx]; status_end = STATUS_BOUNDARY
                 original_end_marker_at_col0 = end_line_text.startswith("**/") or end_line_text.startswith("*/")
                 stripped_end = end_line_text.strip()
                 if is_single_star_end and stripped_end == "*/": status_end = STATUS_MODIFIED
                 elif stripped_end == "**/":
                      if not original_end_marker_at_col0: status_end = STATUS_MODIFIED
                 else: status_end = STATUS_ERROR 
                 if end_line_idx > start_line_idx or len(processed_lines) == 1:
                       processed_lines.append(("**/", status_end))

            processed_blocks_info.append({
                "processed_lines": processed_lines, "start_line_orig": start_line_idx, "end_line_orig": end_line_idx,
                "start_char": start_index, "end_char": end_index_absolute
            })
            for i in current_block_span: processed_spans.add(i)
            processed_char_end = end_index_absolute
        else:
            print(f"Warning: Found '/**' at line {start_line_idx + 1} but no closing tag.")

    return processed_blocks_info

# Possible future functions for block extraction if needed