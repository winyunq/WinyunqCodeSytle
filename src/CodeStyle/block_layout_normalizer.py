# block_layout_normalizer.py (Placeholder for Stage 3)

# Define or import status constants consistently
STATUS_UNMODIFIED = "unmodified" 
STATUS_MODIFIED = "modified"   
STATUS_ERROR = "error"     
STATUS_BOUNDARY = "boundary" 
# Maybe add a specific status for lines affected by T1/T0 normalization?
STATUS_LAYOUT_FIXED = "modified" # Or use STATUS_MODIFIED

# Define or import TagNode class if the parser uses it internally
class TagNode: # Placeholder if structure is complex
    pass 

def normalize_block_layout(segmented_sorted_blocks, config, block_start_orig_line=0):
    """
    Pipeline Stage 3: Normalizes the layout within each logical block from Stage 2.
                      Applies T1 indent to @tag lines based on inferred/assigned level.
                      Applies simplified T2 (fixed space after keyword).
                      Forces T0 (col 4 start) for all subsequent description lines.

    Args:
        segmented_sorted_blocks: List of logical block dicts from Stage 2.
                                 [{'tag_name':..., 'tag_line_content':..., 'description_lines':...}, ...]
        config: Dictionary containing configuration like 'spacesAfterTagKeyword'.
        block_start_orig_line: The original starting line number for mapping.

    Returns:
        A list of dictionaries, representing the lines of the fully layout-normalized block:
        [{'text': str, 'status': str, 'orig_line': int}, ...] 
        Status reflects changes made in *this* stage (T1, T0 subsequent line fixes).
    """
    print(f"--- Running Actual Stage 3: normalize_block_layout (Placeholder) ---") # Debug
    
    final_lines_info = []
    current_orig_line_approx = block_start_orig_line # Approximate mapping
    
    # Add /** boundary (status determined by Stage 1, need to pass it through)
    # For placeholder, assume it was ok
    final_lines_info.append({"text": "/**", "status": STATUS_BOUNDARY, "orig_line": current_orig_line_approx })
    current_orig_line_approx += 1

    # --- Logic to process blocks and apply T1/T0 ---
    # This requires determining the level for each tag block first.
    # Let's use a simple inference based on tag name for this placeholder.
    current_level_stack = [0] # Stack to track nesting depth (L0 is default)
    NESTING_PARENTS = {"@param", "@return", "@details"} # Simplified
    COMMON_NESTED_TAGS = {"@note", "@retval", "@details"}

    for block in segmented_sorted_blocks:
        block_processed_lines = [] # Lines generated for this logical block
        
        if block.get("is_text_block"):
            # Text blocks always follow T0 (start col 4)
            for i, line_content in enumerate(block["lines"]):
                status = STATUS_UNMODIFIED
                # Check if original line had leading spaces (relative to col 4)
                if line_content != line_content.lstrip():
                     status = STATUS_MODIFIED # Indicate stripping occurred
                normalized_text = " * " + line_content.lstrip() 
                block_processed_lines.append({"text": normalized_text, "status": status, "orig_line": current_orig_line_approx + i})
        else: # It's a @tag block
            tag_name = block["tag_name"]
            original_tag_line_content = block["tag_line_content"] # Content after " * " from Stage 1/2
            original_description_lines = block["description_lines"]

            # --- Determine Level (Placeholder Logic) ---
            # Infer level based on simple parent check (needs improvement)
            # This logic ideally belongs in a dedicated parsing step before rendering/layout.
            # For Stage 3 placeholder, let's keep it simple:
            # If tag is nested type AND stack top allows nesting, level = stack_top_level + 1
            # Otherwise, pop stack until level matches or use L0.
            
            # Infer initial T1 spaces from original tag line content
            original_t1_spaces_count = len(original_tag_line_content) - len(original_tag_line_content.lstrip(' '))
            content_after_spaces = original_tag_line_content.lstrip(' ')
            
            # Simple level assignment for placeholder
            target_level = 0 
            if node_stack and tag_name in COMMON_NESTED_TAGS and stack_top_tag in NESTING_PARENTS:
                 target_level = node_stack[-1][1] + 1 # TODO: Access stack info correctly
            # Clamp level for simplicity
            target_level = min(target_level, 2) 

            # --- Apply T1 ---
            t1_spaces = " " * target_level
            
            # --- Apply Simplified T2 ---
            keyword = tag_name[1:]
            spaces_after_keyword = config.get("spacesAfterTagKeyword", 1)
            t2_spaces = " " * spaces_after_keyword

            # --- Extract Arguments and First Description Line ---
            # Need to parse tag_line_content AFTER removing potential original T1/T2 spaces
            tag_match = re.match(r"(@\w+)(\s*)(.*)", content_after_spaces)
            args = ""
            first_desc = ""
            if tag_match:
                _, _, args_and_desc = tag_match.groups()
                # Basic arg extraction
                if tag_name in ["@param", "@retval", "@tparam"]:
                    parts = args_and_desc.lstrip().split(maxsplit=1); args = parts[0] if parts else ""; first_desc = parts[1] if len(parts) > 1 else ""
                else:
                    first_desc = args_and_desc.lstrip() # Assume rest is description

            # --- Construct Normalized Tag Line ---
            normalized_tag_line_content = f"{t1_spaces}{tag_name}"
            if args: normalized_tag_line_content += f" {args}"
            # Add T2 space only if there is a description following
            if first_desc or original_description_lines:
                 normalized_tag_line_content += f"{t2_spaces}{first_desc}"
            
            normalized_tag_line_text = f" * {normalized_tag_line_content}"

            # Determine status for the tag line
            status_tag_line = STATUS_UNMODIFIED
            # Compare normalized markdown part with original (ignoring prefix)
            original_md_content = original_tag_line_content 
            if normalized_tag_line_content != original_md_content:
                status_tag_line = STATUS_MODIFIED
            
            block_processed_lines.append({"text": normalized_tag_line_text, "status": status_tag_line, "orig_line": current_orig_line_approx })
            
            # --- Process Subsequent Description Lines (Force T0) ---
            for i, desc_line in enumerate(original_description_lines):
                status_desc = STATUS_UNMODIFIED
                # Check if original line had leading spaces (relative to col 4)
                if desc_line != desc_line.lstrip():
                     status_desc = STATUS_MODIFIED # Stripped leading spaces
                normalized_desc_line = " * " + desc_line.lstrip()
                block_processed_lines.append({"text": normalized_desc_line, "status": status_desc, "orig_line": current_orig_line_approx + 1 + i})

            # --- Update Nesting Stack (Placeholder) ---
            # TODO: Implement proper stack management based on tag types
            # if tag_name in NESTING_PARENTS: push level
            # else if level decreased: pop stack
                
        # Add processed lines for this block to the final list
        final_lines_info.extend(block_processed_lines)
        # Update approximate original line counter
        current_orig_line_approx += len(block_processed_lines) if block_processed_lines else 1


    # Add **/ boundary (status determined by Stage 1, needs to be passed through)
    # For placeholder, assume it was ok
    final_lines_info.append({"text": "**/", "status": STATUS_BOUNDARY, "orig_line": current_orig_line_approx })

    print(f"--- Stage 3 Result: Processed {len(segmented_sorted_blocks)} logical blocks (Placeholder Layout). ---")
    return final_lines_info

# --- Need TagNode and Debug Output generation if Phase 3 Debug is selected ---
# (Copy TagNode class and _generate_debug_output_internal function here if needed)
# Or have a separate function in this module for debug output generation.
def generate_debug_output_lines(structure, block_start_orig_line=0):
     print("--- Generating Stage 3 Debug Output (Placeholder) ---")
     # Placeholder debug output
     lines = [{"text": "-- Debug Tree Placeholder --", "status": STATUS_DEBUG, "orig_line": block_start_orig_line}]
     for i, node in enumerate(structure): # Assuming structure is list of TagNode from a *real* parser
          lines.append({"text":f" Node {i}: {node!r}", "status": STATUS_DEBUG, "orig_line": block_start_orig_line+i+1})
     lines.append({"text":"-- End Debug --", "status": STATUS_INFO, "orig_line":block_start_orig_line + len(structure)+1})
     return lines