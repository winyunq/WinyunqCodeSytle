"""Explicit plans; per-file atomic replace, backups and crash journal.

There is no portable multi-file atomic filesystem transaction. Cooperating
writers serialize through SQLite. Incomplete crash journals block new writes;
backups are available for deliberate local recovery, not an MCP bypass.
"""
from __future__ import annotations
import difflib
import os
from pathlib import Path
import stat
import tempfile
import time
import uuid

from .cpp import SafeError, canonical, inside, sha
from .doxygen import dump_atomic


def atomic_replace(path: Path, data: bytes | None, old: bytes | None):
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise SafeError("不允许修改符号链接或硬链接文件。")
    if data is None:
        if path.read_bytes() != old:
            raise SafeError("删除前文件变化。")
        path.unlink()
        return
    # Preserve the on-disk filename spelling when replacing a normalized Windows path.
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".doxygenue-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        if (path.read_bytes() if path.exists() else None) != old:
            raise SafeError("提交前文件变化。")
        if old is None:
            # Exclusive creation: never overwrite a file racing a new-symbol add.
            with path.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        else:
            os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Plan:
    def __init__(self, action, kind, default_target, epoch, changes, guards, locks, reason="", locator=None):
        self.id = uuid.uuid4().hex[:20]
        self.action, self.kind, self.default_target = action, kind, default_target
        self.locator = locator
        self.epoch, self.changes, self.guards, self.locks = epoch, changes, guards, locks
        self.reason = reason

    def preview(self, root, fragments=None):
        files = []
        for path, old, new in self.changes:
            before, after = ((old or b"").decode("utf-8-sig"), (new or b"").decode("utf-8-sig"))
            if fragments and path in fragments:
                before, after = fragments[path]
            diff = "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(),
                    fromfile=Path(os.path.relpath(os.path.realpath(path), root)).as_posix() + " / before", tofile=Path(os.path.relpath(os.path.realpath(path), root)).as_posix() + " / after", lineterm="", n=3))
            files.append({"file": Path(os.path.relpath(os.path.realpath(path), root)).as_posix(), "diff": diff[:24000],
                          "diff_truncated": len(diff) > 24000, "before": before[:12000], "after": after[:12000]})
        return {"status": "preview", "preview_id": self.id, "operation": self.action,
                "kind": self.kind, "target": self.locator, "files": files,
                "reason": self.reason, "not_applied": True}

    def apply(self, engine):
        if self.default_target != engine.target:
            raise SafeError("Target 在预览后改变。")
        store, root = engine.store, engine.root
        journals = store.path.parent / "doxygenue-transactions"
        journals.mkdir(parents=True, exist_ok=True)
        with store.transaction():
            import json
            for f in journals.glob("*/journal.json"):
                try:
                    record = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise SafeError(f"事务日志损坏，先人工核查：{f}") from exc
                if record.get("root") == root and record.get("status") not in {"applied", "rolled_back"}:
                    raise SafeError(f"存在未恢复的多文件事务，拒绝继续写入：{f}")
            if self.epoch != store.epoch():
                raise SafeError("锁状态发生变化；必须重新预览。")
            for item in self.locks:
                name, path = item[:2]
                if store.blocked(name, path, all_file=len(item) > 2 and item[2]):
                    raise SafeError("Target 已锁定；MCP 不能解锁。请由用户在 GUI 中明确解锁。")
            expected = {**self.guards, **{p: old for p, old, new in self.changes}}
            for path, raw in expected.items():
                p = Path(path)
                if canonical(p) != path or not inside(path, root) or p.is_symlink():
                    raise SafeError("文件路径边界变化。")
                if p.exists() and (p.stat().st_nlink != 1 or not p.stat().st_mode & stat.S_IWUSR):
                    raise SafeError("硬链接或只读文件不能修改。")
                if (p.read_bytes() if p.exists() else None) != raw:
                    raise SafeError("文件在预览后变化；请重新预览。")
            if self.action == "Delete":
                from .approvals import consume
                consume(engine,self)
            folder = journals / (str(time.time_ns()) + "-" + self.id)
            folder.mkdir()
            record = {"root": root, "preview_id": self.id, "action": self.action,
                      "kind": self.kind, "status": "prepared", "files": []}
            for i, (path, old, new) in enumerate(self.changes):
                backup = folder / f"{i}.before"
                if old is not None:
                    backup.write_bytes(old)
                record["files"].append({"path": path, "existed": old is not None,
                                       "backup": str(backup) if old is not None else None,
                                       "before_hash": None if old is None else sha(old),
                                       "after_hash": None if new is None else sha(new)})
            dump_atomic(folder / "journal.json", record)
            applied = []
            validation = None
            try:
                record["status"] = "applying"
                dump_atomic(folder / "journal.json", record)
                for path, old, new in self.changes:
                    applied.append((path, old, new))
                    atomic_replace(Path(path), new, old)
                if engine.validator:
                    validation = engine.validator.run(root)
                    record["validation"] = validation
                    after = {**self.guards, **{p: new for p, old, new in self.changes}}
                    for path, wanted in after.items():
                        current=Path(path).read_bytes() if Path(path).exists() else None
                        if current!=wanted:
                            raise SafeError("验证命令或外部进程改动了事务源码；保留现场并要求恢复，不声称成功。")
                record["status"] = "applied"
                dump_atomic(folder / "journal.json", record)
            except BaseException:
                rollback_ok = True
                for path, old, new in reversed(applied):
                    try:
                        current = Path(path).read_bytes() if Path(path).exists() else None
                        if current == old:
                            continue
                        if current != new:
                            raise SafeError("失败步骤出现未识别的部分写入/外部变更；保留现场人工恢复。")
                        atomic_replace(Path(path), old, new)
                    except BaseException:
                        rollback_ok = False
                record["status"] = "rolled_back" if rollback_ok else "needs_recovery"
                dump_atomic(folder / "journal.json", record)
                raise
        engine.catalog.fingerprint = ""
        engine.guard.abort()
        engine.plan = None
        return {"status": "applied", "operation": self.action, "kind": self.kind,
                "preview_id": self.id, "files": [Path(os.path.relpath(os.path.realpath(p), root)).as_posix() for p, _, _ in self.changes],
                "journal": str(folder / "journal.json"), "documentation_auto_rewritten": False,
                "validation": validation or {"status": "not_configured"}}
