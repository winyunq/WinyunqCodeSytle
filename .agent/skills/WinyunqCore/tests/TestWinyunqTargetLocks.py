import os
import sys
import tempfile
import unittest


SCRIPT_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from WinyunqTargetLocks import WinyunqTargetLocks
from EditCode import EditCode
from TargetLock import TargetLock


class TestWinyunqTargetLocks(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.workspace = tempfile.mkdtemp()
        self.target = "AExampleActor::UpdateValue"

    def test_lock_is_target_scoped_and_idempotent(self):
        first = WinyunqTargetLocks.lock(
            self.state, self.target, self.workspace, "User-approved API"
        )
        second = WinyunqTargetLocks.lock(
            self.state, self.target, self.workspace, "Different reason"
        )
        self.assertTrue(first["locked"])
        self.assertEqual("User-approved API", second["reason"])
        self.assertFalse(WinyunqTargetLocks.is_locked(
            self.state, "AExampleActor::Other", self.workspace
        ))

    def test_unlock_removes_only_selected_target(self):
        other = "AExampleActor::Other"
        WinyunqTargetLocks.lock(self.state, self.target, self.workspace)
        WinyunqTargetLocks.lock(self.state, other, self.workspace)
        result = WinyunqTargetLocks.unlock(
            self.state, self.target, self.workspace
        )
        self.assertFalse(result["locked"])
        self.assertTrue(WinyunqTargetLocks.is_locked(
            self.state, other, self.workspace
        ))

    def test_locks_are_isolated_by_workspace(self):
        another_workspace = tempfile.mkdtemp()
        WinyunqTargetLocks.lock(self.state, self.target, self.workspace)
        self.assertFalse(WinyunqTargetLocks.is_locked(
            self.state, self.target, another_workspace
        ))

    def test_edit_replace_is_blocked_while_target_is_locked(self):
        WinyunqTargetLocks.lock(self.state, self.target, self.workspace)
        tool = object.__new__(EditCode)
        tool.root = self.workspace
        tool.state = {
            **self.state,
            "pending_edit": {
                "target": self.target,
                "work_path": self.workspace,
            },
        }
        result = tool.replace("OldCall();", "NewCall();")
        self.assertIn("locked by the user", result)

    def test_unlock_requires_exact_confirmation_and_invalidates_ticket(self):
        WinyunqTargetLocks.lock(self.state, self.target, self.workspace)
        tool = object.__new__(TargetLock)
        tool.root = self.workspace
        tool.state = {**self.state, "work_path": self.workspace, "pending_edit": {"id": "old"}}
        tool.save_state = lambda state: None

        rejected = tool.unlock("yes", self.target)
        self.assertIn("Explicit user confirmation", rejected)
        self.assertTrue(WinyunqTargetLocks.is_locked(
            tool.state, self.target, self.workspace
        ))

        accepted = tool.unlock(f"UNLOCK {self.target}", self.target)
        self.assertIn('"locked":false', accepted)
        self.assertIsNone(tool.state["pending_edit"])


if __name__ == "__main__":
    unittest.main()
