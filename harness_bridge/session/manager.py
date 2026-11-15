from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

from harness_bridge.core.exceptions import MaxHopsExceededError
from harness_bridge.core.process import terminate_pid_group
from harness_bridge.core.types import SessionInfo, TaskResult, TaskSpec
from harness_bridge.drivers.registry import get_driver
from harness_bridge.workspace.manager import WorkspaceManager

logger = logging.getLogger("harness-bridge.session")


class SessionManager:
    """Manages multi-turn session lifecycle, durable disk persistence, and distributed circuit breakers."""

    def __init__(
        self,
        workspace_manager: WorkspaceManager | None = None,
        storage_dir: Path | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager or WorkspaceManager()
        if storage_dir is not None:
            self.storage_dir = storage_dir
        else:
            base = os.environ.get("HARNESS_BRIDGE_STORAGE_DIR")
            self.storage_dir = (
                Path(base) / "sessions" if base else Path.home() / ".harness-bridge" / "sessions"
            )

        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            import tempfile

            fallback = Path(tempfile.gettempdir()) / "harness-bridge" / "sessions"
            fallback.mkdir(parents=True, exist_ok=True)
            self.storage_dir = fallback
        self.sessions: dict[str, SessionInfo] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Retrieve or create an async mutex for sequential turn dispatch within a session."""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    def _get_session_dir(self, session_id: str) -> Path:
        """Resolve directory path for a session's persistent journal."""
        session_dir = self.storage_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _save_session(self, session: SessionInfo) -> None:
        """Persist session metadata atomically to disk."""
        try:
            session_dir = self._get_session_dir(session.session_id)
            session_file = session_dir / "session.json"
            tmp_file = session_dir / "session.json.tmp"
            tmp_file.write_text(session.model_dump_json(indent=2), encoding="utf-8")
            tmp_file.replace(session_file)
        except Exception as exc:
            logger.warning("Failed to persist session '%s' to disk: %s", session.session_id, exc)

    def _save_turn(self, session_id: str, turn_number: int, result: TaskResult) -> None:
        """Persist individual turn results to turns/ subdirectory."""
        try:
            turns_dir = self._get_session_dir(session_id) / "turns"
            turns_dir.mkdir(parents=True, exist_ok=True)
            turn_file = turns_dir / f"{turn_number:04d}_turn.json"
            turn_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(
                "Failed to persist turn %d for session '%s': %s", turn_number, session_id, exc
            )

    def _load_session_from_disk(self, session_id: str) -> SessionInfo | None:
        """Attempt to restore session from on-disk JSON journal."""
        session_file = self.storage_dir / session_id / "session.json"
        if not session_file.exists():
            return None
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            session = SessionInfo.model_validate(data)
            self.sessions[session_id] = session
            return session
        except Exception as exc:
            logger.warning("Failed to load session '%s' from disk: %s", session_id, exc)
            return None

    def _resolve_hop_count(self, task: TaskSpec) -> int:
        """Resolve current delegation depth from task spec or inherited environment."""
        env_hop = os.environ.get("HARNESS_BRIDGE_HOP_COUNT")
        if env_hop is not None:
            try:
                return max(task.hop_count, int(env_hop))
            except ValueError:
                pass
        return task.hop_count

    async def execute_task(self, task: TaskSpec) -> TaskResult:
        """Coordinate workspace preparation, loop protection, and driver turn execution."""
        hop_count = self._resolve_hop_count(task)
        if hop_count >= task.max_hops:
            raise MaxHopsExceededError(
                f"Delegation recursion ceiling reached ({hop_count}/{task.max_hops}). Aborting to prevent infinite loops."
            )

        original_session_id = task.session_id
        session_id = original_session_id or str(uuid.uuid4())
        task.session_id = session_id

        # Acquire per-session lock to serialize multiple turns on the same session
        async with self._get_lock(session_id):
            session_dir = self._get_session_dir(session_id)
            log_path = session_dir / "execution.log"

            # Determine target repository directory
            repo_root = Path(task.repo_root).resolve() if task.repo_root else Path.cwd().resolve()

            # Prepare workspace (either inherit repo_root or isolated .worktrees/<id>)
            active_cwd = await self.workspace_manager.prepare_workspace(
                mode=task.workspace_mode,
                repo_root=repo_root,
                session_id=session_id,
            )

            # Update or restore session tracking info
            session = self.get_session(session_id)
            if session:
                task.is_resume = True
                session.turn_count += 1
                session.status = "running"
                if session.harness_session_id and not task.harness_session_id:
                    task.harness_session_id = session.harness_session_id
            else:
                task.is_resume = original_session_id is not None
                session = SessionInfo(
                    session_id=session_id,
                    harness=task.harness,
                    workspace_mode=task.workspace_mode,
                    worktree_path=str(active_cwd) if task.workspace_mode == "worktree" else None,
                    turn_count=1,
                    created_at=time.time(),
                    harness_session_id=task.harness_session_id,
                    status="running",
                )
                self.sessions[session_id] = session

            self._save_session(session)

            # Prepare execution environment with distributed trace propagation
            # Strip interactive session variables to prevent child harnesses from hijacking
            # or crashing active caller sessions (e.g. interactive agy or claude sessions).
            env = dict(os.environ)
            for var in (
                "ANTIGRAVITY_CONVERSATION_ID",
                "ANTIGRAVITY_LS_ADDRESS",
                "ANTIGRAVITY_CSRF_TOKEN",
                "ANTIGRAVITY_TRAJECTORY_ID",
                "ANTIGRAVITY_PROJECT_ID",
                "ANTIGRAVITY_AGENT",
                "ANTIGRAVITY_SOURCE_METADATA",
                "CLAUDE_SESSION_ID",
                "CLAUDE_CONVERSATION_ID",
            ):
                env.pop(var, None)

            env["HARNESS_BRIDGE_TRACE_ID"] = session_id
            env["HARNESS_BRIDGE_HOP_COUNT"] = str(hop_count + 1)

            def pid_callback(pid: int) -> None:
                session.active_pid = pid
                self._save_session(session)

            driver = get_driver(task.harness)
            try:
                result = await driver.run_turn(
                    task,
                    cwd=active_cwd,
                    env=env,
                    log_path=log_path,
                    pid_callback=pid_callback,
                )
            except Exception:
                session.active_pid = None
                session.status = "failed"
                self._save_session(session)
                raise

            # If worktree mode, capture git diff
            if task.workspace_mode == "worktree":
                diff_text = await self.workspace_manager.extract_diff(active_cwd)
                result.diff = diff_text if diff_text.strip() else None

            # Update session state with turn result and native harness ID
            session.active_pid = None
            session.status = result.status
            session.last_turn_result = result
            if result.harness_session_id:
                session.harness_session_id = result.harness_session_id
            if result.driver_metadata:
                session.driver_metadata.update(result.driver_metadata)

            self._save_session(session)
            self._save_turn(session_id, session.turn_count, result)

            return result

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Lookup active or persisted session info."""
        if session_id in self.sessions:
            return self.sessions[session_id]
        return self._load_session_from_disk(session_id)

    async def cancel_session(self, session_id: str) -> bool:
        """Terminate the active process group of a running session and mark it cancelled."""
        session = self.get_session(session_id)
        if not session:
            return False

        if session.active_pid:
            terminate_pid_group(session.active_pid)
            session.active_pid = None

        session.status = "cancelled"
        self._save_session(session)
        return True

    async def close_session(
        self,
        session_id: str,
        repo_root: Path | None = None,
        cleanup_worktree: bool = True,
    ) -> bool:
        """Close session and optionally remove worktree."""
        session = self.get_session(session_id)
        if not session:
            return False

        self.sessions.pop(session_id, None)

        # Clean up ephemeral session sandbox if present
        import shutil
        import tempfile

        sandbox_root = Path(tempfile.gettempdir()) / "harness-bridge" / "sandboxes" / session_id
        if sandbox_root.exists():
            shutil.rmtree(sandbox_root, ignore_errors=True)

        if cleanup_worktree and session.worktree_path and repo_root:
            await self.workspace_manager.cleanup_workspace(
                session_id=session_id,
                worktree_path=Path(session.worktree_path),
                repo_root=repo_root,
            )

        return True
