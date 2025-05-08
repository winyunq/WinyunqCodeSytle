# winyunq_formatter.py (v1.3 - Corrected Import)
import traceback
# Import pipeline modules - Use correct filenames
try:
    # Stage 1: Extracts blocks and normalizes/statuses boundaries
    import block_extractor as block_extractor # <-- ***** 修正这里 *****
    # Stage 2: Normalizes/statuses content line prefixes (needs specific interface)
    import prefix_formatter as prefix_formatter # <-- ***** 假设文件名是这个 *****
    # Stage 3: Parses structure and provides debug output (needs specific interface)
    import tag_parser as tag_parser           # <-- ***** 假设文件名是这个 *****
    # Stage 4: Renders structure to final lines with status (needs specific interface)
    import winyunq_renderer as winyunq_renderer # <-- ***** 假设文件名是这个 *****
    
    # Assume status constants are defined centrally or imported from one place
    # For example, if they are in block_extractor:
    try:
        from block_extractor import STATUS_UNMODIFIED, STATUS_MODIFIED, STATUS_ERROR, STATUS_BOUNDARY
    except ImportError: # Fallback if constants are elsewhere
        print("WARN: Could not import status constants from block_extractor, defining defaults.")
        STATUS_UNMODIFIED = "unmodified"; STATUS_MODIFIED = "modified"; STATUS_ERROR = "error"; STATUS_BOUNDARY = "boundary"

    # Define other statuses used locally or by later stages
    STATUS_RENDERED = getattr(winyunq_renderer,'STATUS_RENDERED', 'rendered')
    STATUS_DEBUG = getattr(tag_parser,'STATUS_DEBUG', 'debug')
    STATUS_INFO = getattr(tag_parser,'STATUS_INFO', 'info') 

except ImportError as e:
    print(f"ERROR: Failed to import one or more pipeline modules: {e}")
    # Define Dummies (same as before)
    # ... (Dummy class definitions remain) ...
    class DummyModule: pass
    block_extractor = DummyModule(); prefix_formatter = DummyModule(); tag_parser = DummyModule(); winyunq_renderer = DummyModule()
    def dummy_extract(*args): return [{"processed_lines": [("/**", "boundary"),(" * Orig line", "unmodified"),("**/", "boundary")], "start_line_orig":0, "end_line_orig":2, "start_char":0, "end_char":20}]
    def dummy_normalize(lines_info): return [{"text":d["text"],"status":STATUS_MODIFIED if i%2==0 else STATUS_UNMODIFIED, "orig_line":d["orig_line"]} for i,d in enumerate(lines_info)]
    def dummy_parse(*args): return [] 
    def dummy_render(*args, **kwargs): return [{"text":"/**", "status":"boundary"}, {"text":" * Rendered Line", "status":"rendered"}, {"text":"**/", "status":"boundary"}] 
    def dummy_debug(*args, **kwargs): return [{"text":"-- Debug --", "status":"debug"}] 
    block_extractor.extract_and_normalize_boundaries = dummy_extract # Use correct function name
    prefix_formatter.normalize_content_prefixes = dummy_normalize # Use correct function name
    tag_parser.parse_to_structure = dummy_parse # Use correct function name
    tag_parser.generate_debug_output_lines = dummy_debug # Use correct function name
    winyunq_renderer.render_structure = dummy_render # Use correct function name
    STATUS_UNMODIFIED="unmodified"; STATUS_MODIFIED="modified"; STATUS_ERROR="error"; STATUS_BOUNDARY="boundary"; STATUS_RENDERED="rendered"; STATUS_DEBUG="debug"; STATUS_INFO="info"


# --- Default Config ---
DEFAULT_CONFIG = { "spacesAfterTagKeyword": 1 }

# --- Main Interface Function ---
def process_code(code_string, config=None):
    # ... (Orchestration logic remains the same, but now calls functions from correctly imported modules) ...
    active_config = DEFAULT_CONFIG.copy()
    if config: active_config.update(config)
    target_phase = active_config.get("target_phase", 4)

    output_structure = {"success": True, "error_message": None, "lines": [], "summary": {}}
    final_output_lines_info = []
    last_processed_orig_line_end = -1
    original_lines = code_string.splitlines()
    processed_orig_lines = set()

    try:
        # --- Pipeline Stage 1 Call (Using correct import) ---
        extracted_blocks_data = block_extractor.extract_and_normalize_boundaries(code_string) 
        # ... (rest of the loop processing blocks) ...
        output_structure["summary"]["blocks_found"] = len(extracted_blocks_data)

        for block_data in extracted_blocks_data:
            block_start_orig = block_data["start_line_orig"]
            block_end_orig = block_data["end_line_orig"]
            stage1_lines_tuples = block_data["processed_lines"]
            stage1_lines_info = [{"text": line, "status": status, "orig_line": block_start_orig + i}
                                 for i, (line, status) in enumerate(stage1_lines_tuples)]

            # Add code BEFORE
            # ... (same logic) ...
            start_code_line = last_processed_orig_line_end + 1
            end_code_line = block_start_orig
            for i in range(start_code_line, end_code_line):
                 if i < len(original_lines) and i not in processed_orig_lines:
                     final_output_lines_info.append({"text": original_lines[i], "status": None, "orig_line": i})
                     processed_orig_lines.add(i)


            current_block_output_lines = stage1_lines_info # Default

            if target_phase >= 2:
                # --- Pipeline Stage 2 Call ---
                try:
                    # Assumes prefix_formatter has this function
                    stage2_lines_info = prefix_formatter.normalize_content_prefixes(stage1_lines_info) 
                    current_block_output_lines = stage2_lines_info 
                except AttributeError: 
                    print("WARN: prefix_formatter.normalize_content_prefixes not available.")
                    # Keep stage1 result if stage 2 fails

                if target_phase >= 3 and output_structure["success"]: 
                    # --- Pipeline Stage 3 Call ---
                    try:
                        # Assumes tag_parser has these functions
                        parsed_structure = tag_parser.parse_to_structure(current_block_output_lines) 

                        if target_phase == 99: # Debug Tree Output
                             current_block_output_lines = tag_parser.generate_debug_output_lines(parsed_structure, block_start_orig)
                        
                        elif target_phase >= 4: # Render final block
                            # --- Pipeline Stage 4 Call ---
                            try:
                                # Assumes winyunq_renderer has this function
                                current_block_output_lines = winyunq_renderer.render_structure(parsed_structure, active_config, block_start_orig)
                            except AttributeError:
                                 print("WARN: winyunq_renderer.render_structure not available.")
                                 # Keep stage 3 result (which might be stage 2 if parse failed)

                    except AttributeError as e_parse:
                         print(f"WARN: tag_parser function not available: {e_parse}")
                         # Keep result from previous stage

            final_output_lines_info.extend(current_block_output_lines)
            for i in range(block_start_orig, block_end_orig + 1):
                 if i < len(original_lines): processed_orig_lines.add(i)
            last_processed_orig_line_end = block_end_orig 

        # Add code AFTER
        # ... (same logic) ...
        start_code_line = last_processed_orig_line_end + 1
        for i in range(start_code_line, len(original_lines)):
             if i not in processed_orig_lines: 
                  final_output_lines_info.append({"text": original_lines[i], "status": None, "orig_line": i})


        output_structure["lines"] = final_output_lines_info
        output_structure["summary"]["lines_modified"] = sum(1 for line in final_output_lines_info if line.get("status") == STATUS_MODIFIED)
        output_structure["summary"]["errors_found"] = sum(1 for line in final_output_lines_info if line.get("status") == STATUS_ERROR)

    except Exception as e:
        # ... (Error handling) ...
        output_structure["success"] = False; output_structure["error_message"] = f"Internal Error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        output_structure["lines"] = [{"text": line, "status": STATUS_ERROR if i==0 else None, "orig_line": i} for i, line in enumerate(code_string.splitlines())]

    return output_structure