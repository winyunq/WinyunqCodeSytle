import json
import os
import sys

try:
    from WinyunqBase import WinyunqAction, WinyunqBase
    from WinyunqTargetEditor import compact_json
    from WinyunqTargetLocks import WinyunqTargetLocks
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqAction, WinyunqBase
    from WinyunqTargetEditor import compact_json
    from WinyunqTargetLocks import WinyunqTargetLocks


class TargetLock(WinyunqBase):
    """Explicit user-controlled locks for logical code Targets."""

    @WinyunqAction(
        "Status",
        "查看当前 Target 是否被用户锁定；读取操作不受锁影响",
        params=[{
            "name": "name",
            "required": False,
            "doc": "Target 全名；省略时使用当前 Target",
        }],
    )
    def status(self, name=None):
        if not name:
            return "Error: No Target is active."
        return compact_json(WinyunqTargetLocks.status(
            self.state,
            name,
            self.state.get("work_path", self.root),
        ))

    @WinyunqAction(
        "Lock",
        "由用户锁定当前 Target；锁定后仍可读取，但禁止源码写入",
        params=[
            {
                "name": "name",
                "required": False,
                "doc": "Target 全名；省略时使用当前 Target",
            },
            {
                "name": "reason",
                "required": False,
                "doc": "可选的用户锁定原因",
            },
        ],
    )
    def lock(self, name=None, reason=""):
        if not name:
            return "Error: No Target is active."
        result = WinyunqTargetLocks.lock(
            self.state,
            name,
            self.state.get("work_path", self.root),
            reason,
        )
        self.state["pending_edit"] = None
        self.save_state(self.state)
        return compact_json(result)

    @WinyunqAction(
        "Unlock",
        "仅在用户明确要求后解锁 Target；confirmation 必须为 UNLOCK 加完整 Target 名",
        params=[
            {
                "name": "name",
                "required": False,
                "doc": "Target 全名；省略时使用当前 Target",
            },
            {
                "name": "confirmation",
                "required": True,
                "doc": "用户确认文本：UNLOCK <完整 Target 名>",
            },
        ],
    )
    def unlock(self, confirmation, name=None):
        if not name:
            return "Error: No Target is active."
        expected = f"UNLOCK {name}"
        if confirmation != expected:
            return f"Error: Explicit user confirmation must exactly equal '{expected}'."
        result = WinyunqTargetLocks.unlock(
            self.state,
            name,
            self.state.get("work_path", self.root),
        )
        self.state["pending_edit"] = None
        self.save_state(self.state)
        return compact_json(result)


if __name__ == "__main__":
    tool = TargetLock()
    if "--manifest" in sys.argv:
        print(json.dumps(tool.get_manifest(), indent=2, ensure_ascii=False))
