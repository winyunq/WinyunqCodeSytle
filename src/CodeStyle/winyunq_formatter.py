# winyunq_formatter.py (v1.6 - Fixed SyntaxError)
import traceback
import re # Ensure re is imported if used internally

# Import pipeline modules
try:
    import block_extractor as block_extractor          # Stage 1
    import tag_segmenter_sorter as tag_parser_s2        # Stage 2
    import block_layout_normalizer as stage3_layout  # Stage 3 <<-- Using this name now
    import winyunq_renderer as winyunq_renderer      # Stage 4
    # Import constants
    from block_extractor import STATUS_UNMODIFIED, STATUS_MODIFIED, STATUS_ERROR, STATUS_BOUNDARY
    STATUS_RENDERED = getattr(winyunq_renderer,'STATUS_RENDERED', 'rendered')
    STATUS_DEBUG = getattr(stage3_layout,'STATUS_DEBUG', 'debug') # Debug status from Stage 3
    STATUS_INFO = getattr(stage3_layout,'STATUS_INFO', 'info')
except ImportError as e:
    # ... Dummies ...
    print(f"ERROR: Failed to import pipeline modules: {e}")
    class DummyModule: pass
    block_extractor = DummyModule(); tag_parser_s2 = DummyModule(); stage3_layout = DummyModule(); winyunq_renderer = DummyModule()
    def dummy_extract(*args): return [{"processed_lines": [("/**", "boundary"),(" * @param b", "unmodified"), (" * @param a", "unmodified"),("**/", "boundary")], "start_line_orig":0, "end_line_orig":3, "start_char":0, "end_char":40}]
    def dummy_segment_sort(lines_info): print("WARN: Using dummy segment/sort"); return [{"tag_name":"@param", "tag_line_content":" a", "description_lines":[]}, {"tag_name":"@param", "tag_line_content":" b", "description_lines":[]}]
    # Dummy for stage 3 (layout normalizer) should return lines info
    def dummy_layout_norm(*args, **kwargs): print("WARN: Using dummy layout normalizer"); return [{"text":"/**", "status":"boundary"}, {"text":" * Layout Norm Line", "status":"modified"}, {"text":"**/", "status":"boundary"}]
    def dummy_render_s4(*args, **kwargs): print("WARN: Using dummy renderer s4"); return [{"text":"/**", "status":"boundary"}, {"text":" * Rendered", "status":"rendered"}, {"text":"**/", "status":"boundary"}]
    def dummy_debug_s3(*args, **kwargs): return [{"text":"-- Debug S3 --", "status":"debug"}]
    block_extractor.extract_and_normalize_block = dummy_extract
    tag_parser_s2.segment_and_sort_tags = dummy_segment_sort
    stage3_layout.normalize_block_layout = dummy_layout_norm # Assign dummy to correct module name
    stage3_layout.generate_debug_output_lines = dummy_debug_s3 # Assign dummy debug
    winyunq_renderer.render_structure = dummy_render_s4
    STATUS_UNMODIFIED="unmodified"; STATUS_MODIFIED="modified"; STATUS_ERROR="error"; STATUS_BOUNDARY="boundary"; STATUS_RENDERED="rendered"; STATUS_DEBUG="debug"; STATUS_INFO="info"


# --- Default Config ---
DEFAULT_CONFIG = { "spacesAfterTagKeyword": 1 }

# --- Main Interface Function ---
def process_code(code_string, config=None):
    """
    STABLE INTERFACE: Orchestrates the Winyunq formatting pipeline by executing
    all necessary stages up to the point required for the target output phase.
    Returns dict {'success':bool, 'error':str|None, 'lines':list[dict]}
    'lines' dicts: {'text': str, 'status': str|None, 'orig_line': int}
    """
    active_config = DEFAULT_CONFIG.copy()
    if config: active_config.update(config)
    
    # --- Corrected Phase Handling ---
    target_phase = active_config.get("target_phase", 4) # Default to render if phase not specified
    try:
        target_phase = int(target_phase)
    except (ValueError, TypeError):
        print(f"Warning: Invalid target_phase value '{active_config.get('target_phase')}', defaulting to 4.")
        target_phase = 4 # Default to 4 on error
    active_config["target_phase"] = target_phase # Ensure config has the validated int phase
    # --- End Corrected Phase Handling ---


    output_structure = {"success": True, "error_message": None, "lines": [], "summary": {}}
    final_output_lines_info = []
    last_processed_orig_line_end = -1
    original_lines = code_string.splitlines()
    processed_orig_lines = set()

    try:
        # --- Pipeline Stage 1: Extract Blocks & Normalize Boundaries/Prefixes ---
        extracted_blocks_data = block_extractor.extract_and_normalize_block(code_string)
        output_structure["summary"]["blocks_found"] = len(extracted_blocks_data)

        for block_data in extracted_blocks_data:
            block_start_orig = block_data["start_line_orig"]
            block_end_orig = block_data["end_line_orig"]
            stage1_processed_tuples = block_data["processed_lines"]
            stage1_lines_info = [{"text": line, "status": status, "orig_line": block_start_orig + i}
                                 for i, (line, status) in enumerate(stage1_processed_tuples)]

            # Add code BEFORE block
            # ... (same logic) ...
            start_code_line = last_processed_orig_line_end + 1; end_code_line = block_start_orig
            for i in range(start_code_line, end_code_line):
                 if i < len(original_lines) and i not in processed_orig_lines:
                     final_output_lines_info.append({"text": original_lines[i], "status": None, "orig_line": i})
                     processed_orig_lines.add(i)

            # --- Pipeline Execution based on Phase ---
            result_stage1 = stage1_lines_info
            result_stage2_blocks = None # Logical blocks from S2
            result_stage3_lines = None  # Normalized lines from S3
            result_stage3_debug_lines = None # Debug lines from S3
            result_stage4_lines = None  # Rendered lines from S4

            current_stage_lines_input = result_stage1 # Input for the next stage

            if target_phase >= 2:
                try:
                    segmented_sorted_blocks = tag_parser_s2.segment_and_sort_tags(current_stage_lines_input) # CALL STAGE 2
                    result_stage2_blocks = segmented_sorted_blocks # Save logical blocks output
                    # NOTE: Stage 2 no longer directly provides lines for output, focus on structure
                except Exception as e_s2:
                    print(f"WARN: Stage 2 (Segment/Sort) failed: {e_s2}"); traceback.print_exc()
                    output_structure["error_message"] = (output_structure.get("error_message") or "") + f"Block@{block_start_orig+1}: Stage 2 failed: {e_s2}\n"
                    # If S2 fails, we cannot proceed to S3/S4 based on structure
                    target_phase = 1 # Force output to Phase 1 result


            if target_phase >= 3 and result_stage2_blocks is not None: # Need blocks from S2
                try:
                    if target_phase == 99: # Debug Tree Output
                         # Debug generator should take the LOGICAL blocks from S2
                         result_stage3_debug_lines = stage3_layout.generate_debug_output_lines(result_stage2_blocks, block_start_orig)
                    else: # Phases 3 and 4 need layout normalization
                        # --- Pipeline Stage 3 Call (Layout Normalization) ---
                        # Input is logical blocks from S2, Output is normalized lines list
                        result_stage3_lines = stage3_layout.normalize_block_layout(result_stage2_blocks, active_config, block_start_orig) # CALL STAGE 3
                        current_stage_lines_input = result_stage3_lines # Update input for next stage
                        
                        if target_phase >= 4 and result_stage3_lines is not None: # Need lines from S3
                            # --- Pipeline Stage 4 Call (Render) ---
                            # Renderer might take the lines from Stage 3 and refine them (e.g. T3)
                            # Or Stage 3 might be the final layout step. Let's assume S4 refines S3 output.
                            # This requires renderer interface to accept lines_info.
                            # Let's adjust the dummy/interface assumption: render takes lines_info from S3.
                            try:
                                 result_stage4_lines = winyunq_renderer.render_refine(result_stage3_lines, active_config, block_start_orig) # CALL STAGE 4 refine
                            except AttributeError: # If renderer only works from structure, call it differently
                                 try: 
                                      # This assumes parser S3 exists and returned structure
                                      parsed_structure_s3 = tag_parser_s3.parse_structure_from_blocks(result_stage2_blocks) # Need to call parser if renderer needs structure
                                      result_stage4_lines = winyunq_renderer.render_structure(parsed_structure_s3, active_config, block_start_orig)
                                 except Exception as e_render_alt:
                                      print(f"WARN: Stage 4 (Render Structure) failed: {e_render_alt}")
                                      # Fallback handled later

                except Exception as e_s3_or_s4:
                     print(f"WARN: Stage 3 or 4 failed: {e_s3_or_s4}"); traceback.print_exc()
                     output_structure["error_message"] = (output_structure.get("error_message") or "") + f"Block@{block_start_orig+1}: Stage 3/4 failed: {e_s3_or_s4}\n"
                     # Fallback handled later


            # --- Select final output for this block based on target_phase and available results ---
            final_block_output = result_stage1 # Default
            if target_phase == 1:   final_block_output = result_stage1
            elif target_phase == 2: 
                # Phase 2 doesn't produce lines directly anymore, show Stage 1
                # Or reconstruct lines from result_stage2_blocks (more complex display logic)
                # Let's keep showing Stage 1 result for Phase 2 selection for simplicity.
                 messagebox.showwarning("Phase 2 Preview", "Phase 2 (Tag Sorting) preview not fully implemented yet. Showing Phase 1 result.") # Inform user
                 final_block_output = result_stage1
            elif target_phase == 99:final_block_output = result_stage3_debug_lines if result_stage3_debug_lines is not None else result_stage1
            elif target_phase == 3: final_block_output = result_stage3_lines if result_stage3_lines is not None else result_stage1
            elif target_phase >= 4: final_block_output = result_stage4_lines if result_stage4_lines is not None else \
                                                          (result_stage3_lines if result_stage3_lines is not None else result_stage1) # Cascade fallback

            # Add the selected output for this block
            final_output_lines_info.extend(final_block_output)
            # Mark original lines processed
            for i in range(block_start_orig, block_end_orig + 1):
                 if i < len(original_lines): processed_orig_lines.add(i)
            last_processed_orig_line_end = block_end_orig

        # Add code AFTER last block
        start_code_line = last_processed_orig_line_end + 1
        for i in range(start_code_line, len(original_lines)):
             if i not in processed_orig_lines:
                  final_output_lines_info.append({"text": original_lines[i], "status": None, "orig_line": i})

        output_structure["lines"] = final_output_lines_info
        output_structure["summary"]["lines_modified"] = sum(1 for line in final_output_lines_info if line.get("status") == STATUS_MODIFIED)
        output_structure["summary"]["errors_found"] = sum(1 for line in final_output_lines_info if line.get("status") == STATUS_ERROR)

    except Exception as e:
        # ... (Global error handling) ...
        output_structure["success"] = False; output_structure["error_message"] = f"Critical Error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        output_structure["lines"] = [{"text": line, "status": STATUS_ERROR if i==0 else None, "orig_line": i} for i, line in enumerate(code_string.splitlines())]

    return output_structure