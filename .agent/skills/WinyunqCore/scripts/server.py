import sys
import json
import os
import traceback
import io

# ==========================================
# Winyunq MCP Entrance (Antigravity Edition)
# STRATEGY: Unified Tool Access
# TACTIC: Clean JSON-RPC over Stdout
# ==========================================

class WinyunqMcpServer:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        if self.script_dir not in sys.path:
            sys.path.append(self.script_dir)

        # Capture original stdout for JSON-RPC communication
        self.out_conn = sys.stdout.buffer
        # Redirect standard stdout to stderr to prevent log pollution in RPC channel
        sys.stdout = sys.stderr

        try:
            from ReadCode import ReadCode
            from WriteCode import WriteCode
            from EditCode import EditCode
            from SetTarget import SetTarget
            from CheckCode import CheckCode

            self.tools = {
                "ReadCode": ReadCode(),
                "WriteCode": WriteCode(),
                "EditCode": EditCode(),
                "SetTarget": SetTarget(),
                "CheckCode": CheckCode()
            }
            self._refresh_shared_state()
        except Exception as e:
            sys.stderr.write(f"Critical: Failed to load tools: {e}\n")
            sys.stderr.write(traceback.format_exc())
            sys.exit(1)

    def run(self):
        sys.stderr.write("Winyunq MCP Server Started.\n")
        sys.stderr.flush()

        # Read from stdin line by line
        input_stream = sys.stdin
        while True:
            try:
                line = input_stream.readline()
                if not line:
                    break

                # Strip potential \r from input (though wrapper usually handles this)
                line = line.strip().lstrip("\ufeff")
                if not line:
                    continue

                request = json.loads(line)
                response = self.process_request(request)
                if response:
                    self.send_response(response)
            except EOFError:
                break
            except Exception as e:
                sys.stderr.write(f"Process Loop Error: {e}\n")
                sys.stderr.flush()

    def process_request(self, request):
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        # 1. Initialization
        if method == "initialize":
            requested_version = params.get("protocolVersion", "2025-06-18")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": requested_version,
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": "winyunq-core-mcp",
                        "version": "1.0.0"
                    },
                    "instructions": (
                        "This server compresses source-code context before it reaches the model. "
                        "Set a Target once, then omit repeated object names. Prefer List and "
                        "Declaration for compact reads. Definition returns comment-free target "
                        "code, Comments returns one requested comment layer, and ReadForEdit "
                        "returns exact target source. Avoid ReadForEdit unless editing requires it."
                    )
                }
            }

        # 2. Tool Discovery (List Tools)
        if method == "tools/list":
            tools_list = []
            for tool_name, tool_inst in self.tools.items():
                manifest = tool_inst.get_manifest()
                for action, info in manifest.items():
                    tools_list.append({
                        "name": f"{tool_name}_{action}",
                        "description": info.get("description", ""),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                p["name"]: {
                                    "type": "string",
                                    "description": p.get("doc", "")
                                } for p in info.get("params", [])
                            },
                            "required": [
                                p["name"] for p in info.get("params", [])
                                if p.get("required")
                            ]
                        }
                    })
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list}
            }

        # 3. Tool Execution (Call Tool)
        if method == "tools/call":
            tool_full_name = params.get("name")
            tool_params = params.get("arguments", {})

            if "_" not in tool_full_name:
                return self.error_resp(req_id, f"Invalid tool name format: {tool_full_name}")

            tool_class_name, action_name = tool_full_name.split("_", 1)
            if tool_class_name not in self.tools:
                return self.error_resp(req_id, f"Tool class {tool_class_name} not found")

            try:
                self._refresh_shared_state()
                # Capture result from tool's invoke method
                # Note: Tools use internal state from WinyunqBase (session_context.json)
                result = self.tools[tool_class_name].invoke(action_name, tool_params)
                self._adopt_tool_state(self.tools[tool_class_name])

                # Winyunq tools usually return strings or structured data
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": str(result)}]
                    }
                }
            except Exception as e:
                return self.error_resp(req_id, f"Execution Error in {tool_full_name}: {str(e)}\n{traceback.format_exc()}")

        # 4. Standard Ping/Notifications (Optional)
        if method == "notifications/initialized":
             return None

        return self.error_resp(req_id, f"Method {method} not supported")

    def _refresh_shared_state(self):
        """Load one current context and share the same state object across every tool."""
        if not self.tools:
            return
        first_tool = next(iter(self.tools.values()))
        shared_state = first_tool.load_state()
        for tool in self.tools.values():
            tool.state = shared_state

    def _adopt_tool_state(self, source_tool):
        """Propagate a Target or scope change immediately without recreating tools."""
        shared_state = source_tool.state
        for tool in self.tools.values():
            tool.state = shared_state

    def error_resp(self, req_id, message):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": message}
        }

    def send_response(self, response):
        content = json.dumps(response, ensure_ascii=False)
        # CRITICAL: Clean \n ending, no \r
        raw_bytes = content.encode('utf-8')
        self.out_conn.write(raw_bytes)
        self.out_conn.write(b'\n')
        self.out_conn.flush()

if __name__ == "__main__":
    # Ensure no buffering for clean real-time interaction
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', line_buffering=True)

    server = WinyunqMcpServer()
    server.run()
