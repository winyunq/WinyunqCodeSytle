# tag_parser_stage2.py (Focus on Tag Blocking and Sorting)
import re

# Define or import status constants if needed for richer output, but focus is structure now
STATUS_INFO = "info" 

# --- Winyunq Tag Order ---
# Define the desired order of top-level tags. Adjust as needed.
WINYUNQ_TAG_ORDER = [
    "@brief", "@details", "@tparam", "@param", "@return", "@retval", # Note: @retval usually nested, but listed here if found at top level
    "@exception", "@throws", "@note", "@warning", "@pre", "@post", 
    "@invariant", "@see", "@deprecated", "@since", "@version", "@author", "@date",
    # Add any other custom or standard tags in desired order
]
# Create a mapping for quick lookup
TAG_ORDER_MAP = {tag: i for i, tag in enumerate(WINYUNQ_TAG_ORDER)}

def segment_and_sort_tags(block_lines_info_stage1):
    """
    Pipeline Stage 2: Segments a normalized block into logical @tag blocks 
                      and sorts the top-level blocks according to Winyunq order.

    Args:
        block_lines_info_stage1: list of dicts from stage 1 (prefix/boundary norm)
                                 [{'text': str, 'status': str, 'orig_line': int}, ...]

    Returns:
        A list of dictionaries, where each dictionary represents a logical block:
        - Text Block: {'is_text_block': True, 'lines': list[str]} 
        - Tag Block:  {'tag_name': str, 'tag_line_content': str, 'description_lines': list[str]}
        The list is sorted according to WINYUNQ_TAG_ORDER for top-level tags.
    """
    
    tag_blocks = []
    initial_description = []
    current_tag_block = None 
    first_tag_encountered = False

    # Iterate through normalized lines (skip /** and **/)
    for line_info in block_lines_info_stage1[1:-1]:
        line_text = line_info["text"]
        
        # Extract markdown content area (text after " * ")
        markdown_content = ""
        if line_text.startswith(" * "):
            markdown_content = line_text[3:]
        elif line_text == " *": # Keep empty lines relative content empty
             markdown_content = ""
        # Ignore malformed lines without '*' prefix? Stage 1 should fix them.
        # For safety, maybe handle lines not starting with ' * '?
        elif line_text.strip() != "": # Non-empty line without proper prefix? Problem from Stage 1?
             print(f"WARN (Stage 2): Encountered unexpected line format: {line_text}")
             # Treat it as content for robustness
             markdown_content = line_text.strip() # Take stripped content

        # --- Identify @tag start ---
        # Check if the markdown content (ignoring initial spaces for T1) starts with @
        content_lstripped = markdown_content.lstrip()
        is_tag_start = content_lstripped.startswith('@')
        
        tag_name = None
        if is_tag_start:
            tag_match = re.match(r"(@\w+)", content_lstripped)
            if tag_match:
                tag_name = tag_match.group(1)

        if tag_name: # It's a new @tag line
            first_tag_encountered = True
            # Finish the previous block (if any)
            if current_tag_block:
                tag_blocks.append(current_tag_block)
            
            # Start the new block
            current_tag_block = {
                "tag_name": tag_name,
                # Store the markdown_content part of the tag line itself
                # This still includes original T1/T2 spaces at this stage
                "tag_line_content": markdown_content, 
                "description_lines": [] # Start collecting description lines for this tag
            }
        else: # It's a description line or initial description
            if not first_tag_encountered:
                # Belongs to the initial description block before any tag
                initial_description.append(markdown_content)
            elif current_tag_block:
                # Belongs to the description of the current tag
                current_tag_block["description_lines"].append(markdown_content)
            # else: description line appeared after last tag ended? Orphan line? Ignore for now.

    # Add the last collected tag block
    if current_tag_block:
        tag_blocks.append(current_tag_block)

    # --- Construct the final list with initial description ---
    final_blocks = []
    if initial_description:
        # Remove trailing empty strings from initial description
        while initial_description and initial_description[-1] == "":
            initial_description.pop()
        if initial_description: # Add only if non-empty after stripping trailing blanks
             final_blocks.append({"is_text_block": True, "lines": initial_description})

    # --- Sort the Tag Blocks ---
    def get_sort_key(block):
        if block.get("is_text_block"):
            return -1 # Text block always comes first
        tag_name = block.get("tag_name")
        # Return the index from the order map, use a large number for unknown tags
        return TAG_ORDER_MAP.get(tag_name, float('inf'))

    # Separate text blocks and tag blocks for sorting
    text_blocks = [b for b in tag_blocks if b.get("is_text_block")] # Should be max 1 if logic is right
    tag_only_blocks = [b for b in tag_blocks if not b.get("is_text_block")]

    sorted_tag_blocks = sorted(tag_only_blocks, key=get_sort_key)
    
    # Combine initial description (if any) and sorted tag blocks
    final_blocks.extend(sorted_tag_blocks)

    return final_blocks

# --- Example Usage (if run directly) ---
if __name__ == '__main__':
    # Example input simulating Stage 1 output
    stage1_output_example = [
        {"text": "/**", "status": "boundary", "orig_line": 0},
        {"text": " * Initial description line.", "status": "unmodified", "orig_line": 1},
        {"text": " * @param b Second param.", "status": "modified", "orig_line": 2}, # Prefix was fixed maybe
        {"text": " * @brief A brief description.", "status": "unmodified", "orig_line": 3},
        {"text": " * More detail for brief.", "status": "unmodified", "orig_line": 4},
        {"text": " * @param a First param.", "status": "unmodified", "orig_line": 5},
        {"text": " *   Note for param a (orig indent).", "status": "unmodified", "orig_line": 6}, # Still has orig indent here
        {"text": " * @unknown Tag here.", "status": "unmodified", "orig_line": 7},
        {"text": "**/", "status": "boundary", "orig_line": 8}
    ]

    segmented_blocks = segment_and_sort_tags(stage1_output_example)
    
    print("--- Segmented and Sorted Blocks ---")
    for block in segmented_blocks:
        if block.get("is_text_block"):
            print("TextBlock:")
            for line in block["lines"]: print(f"  '{line}'")
        else:
            print(f"TagBlock: {block['tag_name']}")
            print(f"  Tag Line Content: '{block['tag_line_content']}'")
            print(f"  Description Lines:")
            for line in block["description_lines"]: print(f"    '{line}'")
        print("-----")