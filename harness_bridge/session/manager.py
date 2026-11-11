from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from harness_bridge.core.exceptions import MaxHopsExceededError
from harness_bridge.core.types import SessionInfo, TaskResult, TaskSpec
from harness_bridge.drivers.registry import get_driver
from harness_bridge.workspace.manager import WorkspaceManager


class SessionManager:
    """Manages multi-turn session lifecycle, workspace isolation, and distributed circuit breakers."""

    def __init__(self, workspace_manager: WorkspaceManager | None = None) -> None:
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.sessions: dict[str, SessionInfo] = {}

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

        session_id = task.session_id or str(uuid.uuid4())
        task.session_id = session_id

        # Determine target repository directory
        repo_root = Path(task.repo_root).resolve() if task.repo_root else Path.cwd().resolve()

        # Prepare workspace (either inherit repo_root or isolated .worktrees/<id>)
        active_cwd = await self.workspace_manager.prepare_workspace(
            mode=task.workspace_mode,
            repo_root=repo_root,
            session_id=session_id,
        )

        # Update or create session tracking info
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionInfo(
                session_id=session_id,
                harness=task.harness,
                workspace_mode=task.workspace_mode,
                worktree_path=str(active_cwd) if task.workspace_mode == "worktree" else None,
                turn_count=1,
                created_at=time.time(),
            )
        else:
            self.sessions[session_id].turn_count += 1

        # Prepare execution environment with distributed trace propagation
        env = dict(os.environ)
        env["HARNESS_BRIDGE_TRACE_ID"] = session_id
        env["HARNESS_BRIDGE_HOP_COUNT"] = str(hop_count + 1)

        # Execute driver turn
        driver = get_driver(task.harness)
        result = await driver.run_turn(task, cwd=active_cwd, env=env)

        # If worktree mode, capture git diff
        if task.workspace_mode == "worktree":
            diff_text = await self.workspace_manager.extract_diff(active_cwd)
            result.diff = diff_text if diff_text.strip() else None

        return result

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Lookup active session info."""
        return self.sessions.get(session_id)

    async def close_session(
        self,
        session_id: str,
        repo_root: Path | None = None,
        cleanup_worktree: bool = True,
    ) -> bool:
        """Close session and optionally remove worktree."""
        session = self.sessions.pop(session_id, None)
        if not session:
            return False

        if cleanup_worktree and session.worktree_path and repo_root:
            await self.workspace_manager.cleanup_workspace(
                session_id=session_id,
                worktree_path=Path(session.worktree_path),
                repo_root=repo_root,
            )

        return True
