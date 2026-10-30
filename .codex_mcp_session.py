import json
import sys

from maintenance.client import Client


client = Client(
    "D:/UE5Project/Winyunq",
    "C:/Strawberry/c/bin/doxygen.exe",
    "C:/Users/winyunq/Tools/UnrealMaintenanceMCP-0.1.0/UnrealMaintenanceMCP/local-winyunq/state.sqlite3",
    name="Codex Tank Cleanup",
    profile="C:/Users/winyunq/Tools/UnrealMaintenanceMCP-0.1.0/UnrealMaintenanceMCP/local-winyunq/winyunq-project-profile.json",
)
print(json.dumps({"ready": True}), flush=True)
try:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("tool") == "quit":
                break
            result = client.call(request["tool"], **request.get("args", {}))
            print(json.dumps({"result": result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
finally:
    client.close()
