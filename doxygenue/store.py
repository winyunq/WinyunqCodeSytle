"""Cross-process locks and local-only audit; Target/editor state never lives here.

SQLite's BEGIN IMMEDIATE serializes cooperating writers and GUI lock changes.
The DB is a policy boundary for MCP, not a sandbox against code running as the
same OS user. There is intentionally no RPC/CLI unlock route.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Iterator

from .cpp import canonical, inside, SafeError, sha


def default_db() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "WinyunqContext" / "state.sqlite3"


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_db()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO metadata VALUES ('epoch','0');
        CREATE TABLE IF NOT EXISTS locks (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, root TEXT NOT NULL,
            locations TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, legacy INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL,
            root TEXT NOT NULL, session TEXT NOT NULL, client TEXT NOT NULL,
            method TEXT NOT NULL, request TEXT NOT NULL, response TEXT NOT NULL,
            elapsed_ms REAL NOT NULL, request_chars INTEGER NOT NULL,
            response_chars INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS audit_root ON audit(root,seq);
        """)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self) -> None:
        self.db.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def epoch(self) -> int:
        return int(self.db.execute("SELECT value FROM metadata WHERE key='epoch'").fetchone()[0])

    def _bump(self) -> None:
        self.db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='epoch'")

    def locks(self, root: str | None = None) -> list[dict]:
        records = [dict(row) for row in self.db.execute("SELECT * FROM locks WHERE active=1 ORDER BY created")]
        for record in records:
            record["locations"] = json.loads(record["locations"])
        if root:
            records = [r for r in records if inside(r["root"], root) or inside(root, r["root"]) or any(inside(p["path"], root) for p in r["locations"])]
        return records

    def blocked(self, name: str, path: str, *, all_file: bool = False) -> list[dict]:
        result = []
        path = canonical(path)
        for record in self.locks():
            matching_location = any(canonical(loc["path"]) == path for loc in record["locations"])
            # Names are resolved names, never client-supplied aliases or scope IDs.
            same_object = record["name"] == name and (matching_location or inside(path, record["root"]))
            unresolved_legacy = record["legacy"] and inside(path, record["root"])
            if same_object or unresolved_legacy or (all_file and matching_location):
                result.append(record)
        return result

    def lock(self, root: str, name: str, locations: list[dict], reason: str = "") -> dict:
        with self.transaction():
            existing = self.blocked(name, locations[0]["path"])
            if existing:
                return existing[0]
            lock_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO locks(id,name,root,locations,reason,created) VALUES(?,?,?,?,?,?)", (lock_id, name, canonical(root), json.dumps(locations), reason[:1000], time.time()))
            self._bump()
        return next(r for r in self.locks() if r["id"] == lock_id)

    def user_unlock(self, lock_id: str) -> None:
        """Trusted in-process GUI callback ONLY; never exposed in the MCP registry.

        This method does not claim to authenticate an OS identity. A person must
        confirm in the GUI. Preventing same-user shell/DB edits needs OS isolation.
        """
        with self.transaction():
            row = self.db.execute("SELECT active FROM locks WHERE id=?", (lock_id,)).fetchone()
            if row is None or not row[0]:
                raise SafeError("锁记录不存在或已经解除。")
            self.db.execute("UPDATE locks SET active=0 WHERE id=?", (lock_id,))
            self._bump()

    def import_legacy(self, root: str) -> None:
        path = Path(root) / "Gemini_Config.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            locks = data.get("target_locks", {})
            if not isinstance(locks, dict):
                raise ValueError("target_locks 必须是对象")
        except (OSError, UnicodeError, ValueError) as exc:
            raise SafeError(f"旧配置无法读取，不能确认旧锁；请在 GUI 启动前人工检查 {path.name}: {exc}") from exc
        with self.transaction():
            for scope, records in locks.items():
                if not isinstance(records, dict):
                    raise SafeError("旧锁格式错误；拒绝忽略。")
                for name, record in records.items():
                    fingerprint = "legacy:" + sha(json.dumps([canonical(path), scope, name, record], ensure_ascii=False, sort_keys=True).encode())
                    if self.db.execute("SELECT 1 FROM metadata WHERE key=?", (fingerprint,)).fetchone():
                        continue
                    # No guessing during migration. Conservative scope lock survives
                    # missing/ambiguous names; GUI explicitly reviews and releases it.
                    self.db.execute("INSERT INTO locks(id,name,root,locations,reason,created,legacy) VALUES(?,?,?,?,?,?,1)", (uuid.uuid4().hex, str(name), canonical(scope), "[]", "从 PR #2 迁移：需人工复核的保守范围锁。" + str(record.get("reason", "") if isinstance(record, dict) else ""), time.time()))
                    self.db.execute("INSERT INTO metadata VALUES(?,?)", (fingerprint, "imported"))
                    self._bump()

    def audit(self, root: str, session: str, client: str, request: str, response: str, elapsed_ms: float, method: str) -> None:
        with self.transaction():
            self.db.execute("INSERT INTO audit(time,root,session,client,method,request,response,elapsed_ms,request_chars,response_chars) VALUES(?,?,?,?,?,?,?,?,?,?)", (time.time(), root, session, client[:200], method, request, response, elapsed_ms, len(request), len(response)))
            # Bounded local retention. Notifications also have rows (empty response).
            self.db.execute("DELETE FROM audit WHERE seq <= (SELECT MAX(seq)-2000 FROM audit)")

    def read_audit(self, root: str, after: int = 0, limit: int = 200) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM audit WHERE root=? AND seq>? ORDER BY seq LIMIT ?", (canonical(root), after, max(1, min(limit, 1000))))]
