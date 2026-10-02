"""Durable SQLite checkpoints with separate cancellation and worker leases."""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS tasks "
                "(id TEXT PRIMARY KEY, state TEXT NOT NULL, cancelled INTEGER DEFAULT 0, "
                "owner TEXT, lease_until REAL DEFAULT 0)"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create(self, state: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO tasks(id,state) VALUES (?,?)", (state["id"], json.dumps(state)))

    def save(self, state: dict[str, Any], owner: str | None = None) -> None:
        state["updated_at"] = utcnow()
        with self.connection() as db:
            if owner:
                cursor = db.execute(
                    "UPDATE tasks SET state=?,lease_until=? WHERE id=? AND owner=?",
                    (json.dumps(state), time.time() + 2400, state["id"], owner),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Task worker lease was lost")
            else:
                db.execute("UPDATE tasks SET state=? WHERE id=?", (json.dumps(state), state["id"]))

    def get(self, task_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT state,cancelled FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        state = json.loads(row[0])
        state["cancel_requested"] = bool(row[1])
        return state

    def list(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT state FROM tasks ORDER BY rowid DESC LIMIT 100").fetchall()
        return [json.loads(row[0]) for row in rows]

    def cancel(self, task_id: str) -> None:
        with self.connection() as db:
            if db.execute("UPDATE tasks SET cancelled=1 WHERE id=?", (task_id,)).rowcount != 1:
                raise KeyError(task_id)
            # The update holds the write lock: a concurrent worker cannot claim/save
            # between this fresh read and the unowned queued-task transition.
            encoded, owner = db.execute(
                "SELECT state,owner FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            state = json.loads(encoded)
            if owner is None and state["status"] in {"queued", "interrupted"}:
                state.update(
                    status="cancelled", phase="done", summary="Task cancelled.", updated_at=utcnow()
                )
                db.execute("UPDATE tasks SET state=? WHERE id=?", (json.dumps(state), task_id))

    def is_cancelled(self, task_id: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT cancelled FROM tasks WHERE id=?", (task_id,)).fetchone()
        return bool(row and row[0])

    def claim(self, task_id: str, owner: str) -> bool:
        with self.connection() as db:
            cursor = db.execute(
                "UPDATE tasks SET owner=?,lease_until=? "
                "WHERE id=? AND (owner IS NULL OR lease_until<?)",
                (owner, time.time() + 2400, task_id, time.time()),
            )
        return cursor.rowcount == 1

    def release(self, task_id: str, owner: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE tasks SET owner=NULL,lease_until=0 WHERE id=? AND owner=?", (task_id, owner)
            )

    def recover_startup(self) -> None:
        """Single-process startup: mark abandoned runs; never auto-spend inference."""
        with self.connection() as db:
            for task_id, encoded in db.execute("SELECT id,state FROM tasks").fetchall():
                state = json.loads(encoded)
                if state["status"] == "running":
                    state["status"] = "interrupted"
                    state["summary"] = (
                        "Worker stopped; resume explicitly from the durable checkpoint."
                    )
                    db.execute("UPDATE tasks SET state=? WHERE id=?", (json.dumps(state), task_id))
            db.execute("UPDATE tasks SET owner=NULL,lease_until=0")
