import json
import os
import sys

try:
    from WinyunqBase import WinyunqAction, WinyunqBase
    from WinyunqTargetEditor import WinyunqTargetEditor, compact_json
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqAction, WinyunqBase
    from WinyunqTargetEditor import WinyunqTargetEditor, compact_json


class EditCode(WinyunqBase):
    """Stateful, Target-scoped code editing without whole-file replacement."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.editor = WinyunqTargetEditor()

    @WinyunqAction(
        "Prepare",
        "读取当前函数的无注释实现并记住源码版本，供后续小范围替换",
        params=[{
            "name": "name",
            "required": False,
            "doc": "函数全名；省略时使用当前 Target",
        }],
    )
    def prepare(self, name=None):
        if not name:
            return "Error: No function Target is active."
        try:
            prepared = self.editor.prepare(
                name,
                self.state.get("work_path", self.root),
                self.state.get("filters", []),
            )
        except (OSError, UnicodeError, ValueError) as error:
            return f"Error: {error}"
        self.state["pending_edit"] = prepared["ticket"]
        self.save_state(self.state)
        return compact_json({
            "target": prepared["target"],
            "revision": prepared["ticket"]["id"],
            "implementation": prepared["implementation"],
        })

    @WinyunqAction(
        "Preview",
        "预览当前 Target 内的代码片段替换，不写入文件",
        params=[
            {"name": "old_code", "required": True, "doc": "待替换的现有代码片段"},
            {"name": "new_code", "required": True, "doc": "不含注释的新代码片段"},
        ],
    )
    def preview(self, old_code, new_code):
        ticket = self.state.get("pending_edit")
        try:
            return compact_json(self.editor.preview(ticket, old_code, new_code))
        except (OSError, UnicodeError, ValueError) as error:
            return f"Error: {error}"

    @WinyunqAction(
        "Replace",
        "仅在当前函数体内替换一段代码；保留签名、注释和其他函数",
        params=[
            {"name": "old_code", "required": True, "doc": "待替换的现有代码片段"},
            {"name": "new_code", "required": True, "doc": "不含注释的新代码片段"},
        ],
    )
    def replace(self, old_code, new_code):
        ticket = self.state.get("pending_edit")
        try:
            result = self.editor.replace(ticket, old_code, new_code)
        except (OSError, UnicodeError, ValueError) as error:
            return f"Error: {error}"
        self.state["pending_edit"] = result.pop("ticket")
        self.save_state(self.state)
        result["revision"] = self.state["pending_edit"]["id"]
        return compact_json(result)

    @WinyunqAction("Abort", "丢弃当前编辑事务，不修改源码", params=[])
    def abort(self):
        self.state["pending_edit"] = None
        self.save_state(self.state)
        return "Edit transaction cleared."

    @WinyunqAction("Status", "查看当前 Target 编辑事务", params=[])
    def status(self):
        ticket = self.state.get("pending_edit")
        if not ticket:
            return compact_json({"pending_edit": None})
        return compact_json({
            "pending_edit": {
                "target": ticket.get("target"),
                "file": ticket.get("file"),
                "revision": ticket.get("id"),
            }
        })


if __name__ == "__main__":
    tool = EditCode()
    if "--manifest" in sys.argv:
        print(json.dumps(tool.get_manifest(), indent=2, ensure_ascii=False))
