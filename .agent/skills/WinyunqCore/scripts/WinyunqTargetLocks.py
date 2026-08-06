import os
from datetime import datetime, timezone


class WinyunqTargetLocks:
    """Persist explicit user locks per workspace and logical Target."""

    @staticmethod
    def workspace_key(work_path):
        return os.path.normcase(os.path.abspath(work_path))

    @classmethod
    def status(cls, state, target, work_path):
        workspace = cls.workspace_key(work_path)
        record = (
            state.get("target_locks", {})
            .get(workspace, {})
            .get(target)
        )
        if not record:
            return {
                "target": target,
                "workspace": workspace,
                "locked": False,
            }
        return {
            "target": target,
            "workspace": workspace,
            "locked": True,
            "reason": record.get("reason", ""),
            "locked_at": record.get("locked_at"),
        }

    @classmethod
    def is_locked(cls, state, target, work_path):
        return cls.status(state, target, work_path)["locked"]

    @classmethod
    def lock(cls, state, target, work_path, reason=""):
        workspace = cls.workspace_key(work_path)
        locks = state.setdefault("target_locks", {})
        workspace_locks = locks.setdefault(workspace, {})
        existing = workspace_locks.get(target)
        if existing:
            return cls.status(state, target, work_path)
        workspace_locks[target] = {
            "reason": reason.strip(),
            "locked_at": datetime.now(timezone.utc).isoformat(),
        }
        return cls.status(state, target, work_path)

    @classmethod
    def unlock(cls, state, target, work_path):
        workspace = cls.workspace_key(work_path)
        workspace_locks = state.setdefault("target_locks", {}).get(workspace, {})
        workspace_locks.pop(target, None)
        if not workspace_locks:
            state.get("target_locks", {}).pop(workspace, None)
        return cls.status(state, target, work_path)
