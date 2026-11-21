from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path

from harness_bridge.core.types import (
    TaskRecord,
    TaskResult,
    WorkerInfo,
)

logger = logging.getLogger("harness-bridge.relay.store")


class RelayStore:
    """Durable SQLite storage engine for tasks, leases, worker presence, and session affinity."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                import tempfile

                self.db_path = Path(tempfile.gettempdir()) / "harness-bridge" / self.db_path.name
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            env_db = os.environ.get("HARNESS_BRIDGE_RELAY_DB")
            if env_db:
                self.db_path = Path(env_db)
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                base = os.environ.get("HARNESS_BRIDGE_STORAGE_DIR")
                base_dir = Path(base) if base else Path.home() / ".harness-bridge"
                try:
                    base_dir.mkdir(parents=True, exist_ok=True)
                    self.db_path = base_dir / "relay.db"
                except OSError:
                    import tempfile

                    self.db_path = Path(tempfile.gettempdir()) / "harness-bridge" / "relay.db"
                    self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    workspace_mode TEXT NOT NULL DEFAULT 'inherit',
                    repo_root TEXT,
                    timeout_seconds INTEGER NOT NULL DEFAULT 300,
                    detach INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    worker_id TEXT,
                    lease_expires_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    result_json TEXT,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_harness ON tasks(harness);

                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    harnesses_json TEXT NOT NULL,
                    connected_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    device_name TEXT
                );

                CREATE TABLE IF NOT EXISTS session_affinity (
                    session_id TEXT PRIMARY KEY,
                    worker_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def save_task(self, task: TaskRecord) -> None:
        """Insert or update a task record."""
        now = time.time()
        result_json = task.result.model_dump_json() if task.result else None
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, session_id, harness, prompt, workspace_mode,
                    repo_root, timeout_seconds, detach, status, worker_id,
                    lease_expires_at, created_at, updated_at, result_json, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    worker_id = excluded.worker_id,
                    lease_expires_at = excluded.lease_expires_at,
                    updated_at = excluded.updated_at,
                    result_json = excluded.result_json,
                    error = excluded.error;
                """,
                (
                    task.task_id,
                    task.session_id,
                    task.harness,
                    task.prompt,
                    task.workspace_mode,
                    task.repo_root,
                    task.timeout_seconds,
                    1 if task.detach else 0,
                    task.status,
                    task.worker_id,
                    task.lease_expires_at,
                    task.created_at or now,
                    now,
                    result_json,
                    task.error,
                ),
            )

    def get_task(self, task_id: str) -> TaskRecord | None:
        """Fetch task record by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def get_latest_task_for_session(self, session_id: str) -> TaskRecord | None:
        """Fetch the most recently updated task for a given session."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def claim_task(self, task_id: str, worker_id: str, lease_seconds: float = 45.0) -> bool:
        """Atomically claim a pending or offered task lease for a worker."""
        now = time.time()
        expires = now + lease_seconds
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'assigned',
                    worker_id = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                  AND (status IN ('pending', 'offered') OR (status = 'assigned' AND lease_expires_at < ?));
                """,
                (worker_id, expires, now, task_id, now),
            )
            return cursor.rowcount > 0

    def renew_lease(self, task_id: str, worker_id: str, lease_seconds: float = 45.0) -> bool:
        """Renew active lease for worker."""
        now = time.time()
        expires = now + lease_seconds
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'running',
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                  AND worker_id = ?
                  AND status IN ('assigned', 'running');
                """,
                (expires, now, task_id, worker_id),
            )
            return cursor.rowcount > 0

    def complete_task(self, task_id: str, worker_id: str, result: TaskResult) -> bool:
        """Mark task completed with result."""
        now = time.time()
        result_json = result.model_dump_json()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'completed',
                    result_json = ?,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE task_id = ? AND worker_id = ? AND status IN ('assigned', 'running');
                """,
                (result_json, now, task_id, worker_id),
            )
            return cursor.rowcount > 0

    def fail_task(self, task_id: str, worker_id: str, error: str) -> bool:
        """Mark task failed with error."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'failed',
                    error = ?,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE task_id = ? AND worker_id = ? AND status IN ('assigned', 'running');
                """,
                (error, now, task_id, worker_id),
            )
            return cursor.rowcount > 0

    def cancel_task(self, task_id: str) -> bool:
        """Mark task cancelled."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'cancelled',
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE task_id = ? AND status NOT IN ('completed', 'failed');
                """,
                (now, task_id),
            )
            return cursor.rowcount > 0

    def register_worker(self, worker: WorkerInfo) -> None:
        """Register or update worker presence and capabilities."""
        now = time.time()
        harnesses_json = json.dumps(worker.harnesses)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workers (worker_id, harnesses_json, connected_at, last_seen_at, is_active, device_name)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    harnesses_json = excluded.harnesses_json,
                    last_seen_at = excluded.last_seen_at,
                    is_active = 1,
                    device_name = excluded.device_name;
                """,
                (
                    worker.worker_id,
                    harnesses_json,
                    worker.connected_at or now,
                    now,
                    worker.device_name,
                ),
            )

    def heartbeat_worker(self, worker_id: str) -> None:
        """Update worker liveness."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE workers SET last_seen_at = ?, is_active = 1 WHERE worker_id = ?",
                (now, worker_id),
            )

    def deactivate_worker(self, worker_id: str) -> None:
        """Mark worker inactive on disconnect."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE workers SET is_active = 0 WHERE worker_id = ?",
                (worker_id,),
            )

    def list_active_workers(self, harness: str | None = None) -> list[WorkerInfo]:
        """List active connected workers matching optional harness filter."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM workers WHERE is_active = 1").fetchall()
            workers: list[WorkerInfo] = []
            for r in rows:
                harnesses = json.loads(r["harnesses_json"])
                if harness and harness not in harnesses:
                    continue
                workers.append(
                    WorkerInfo(
                        worker_id=r["worker_id"],
                        harnesses=harnesses,
                        connected_at=r["connected_at"],
                        last_seen_at=r["last_seen_at"],
                        is_active=bool(r["is_active"]),
                        device_name=r["device_name"],
                    )
                )
            return workers

    def set_session_affinity(self, session_id: str, worker_id: str) -> None:
        """Bind session to worker for conversational continuity."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO session_affinity (session_id, worker_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    worker_id = excluded.worker_id,
                    updated_at = excluded.updated_at;
                """,
                (session_id, worker_id, now, now),
            )

    def get_session_affinity(self, session_id: str) -> str | None:
        """Retrieve assigned worker_id for session, if any."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT worker_id FROM session_affinity WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row["worker_id"] if row else None

    def clean_expired_leases(self, grace_period_seconds: float = 30.0) -> list[str]:
        """Mark tasks with expired leases beyond grace period as timeout/failed."""
        now = time.time()
        cutoff = now - grace_period_seconds
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT task_id FROM tasks
                WHERE status IN ('assigned', 'running')
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ?;
                """,
                (cutoff,),
            ).fetchall()
            expired_ids = [r["task_id"] for r in rows]
            if expired_ids:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'timeout',
                        error = 'Worker lease expired; worker heartbeat not received.',
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE task_id IN ({});
                    """.format(",".join("?" * len(expired_ids))),
                    [now] + expired_ids,
                )
            return expired_ids

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        result = None
        if row["result_json"]:
            try:
                result = TaskResult.model_validate_json(row["result_json"])
            except Exception:
                pass
        return TaskRecord(
            task_id=row["task_id"],
            session_id=row["session_id"],
            harness=row["harness"],
            prompt=row["prompt"],
            workspace_mode=row["workspace_mode"],
            repo_root=row["repo_root"],
            timeout_seconds=row["timeout_seconds"],
            detach=bool(row["detach"]),
            status=row["status"],
            worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result=result,
            error=row["error"],
        )
