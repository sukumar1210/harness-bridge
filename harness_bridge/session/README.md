# Session Manager (`harness_bridge.session`)

## Overview
The `harness_bridge.session` module provides multi-turn conversational session tracking, workspace isolation coordination, and distributed recursion circuit breakers for agent harnesses. It manages the lifecycle of AI agent interactions, tracks turn counts, propagates distributed tracing headers, and orchestrates workspace preparation and cleanup across turns.

## Interface
- `SessionManager(workspace_manager: WorkspaceManager | None = None)`: Initializes the session manager with an optional workspace manager instance and an in-memory session registry (`sessions`).
- `async execute_task(task: TaskSpec) -> TaskResult`: Coordinates turn execution, recursion hop limit validation, workspace allocation (worktree or inherit), environment variable propagation, driver delegation, and git diff extraction.
- `get_session(session_id: str) -> SessionInfo | None`: Retrieves tracking metadata (`SessionInfo`) for an active or previously executed session.
- `async close_session(session_id: str, repo_root: Path | None = None, cleanup_worktree: bool = True) -> bool`: Terminates a session, purges tracking info, and optionally removes isolated git worktrees from disk.

## Invariants
- **Delegation Recursion Ceiling**: Aborts execution with `MaxHopsExceededError` if `hop_count >= task.max_hops` to prevent infinite inter-agent recursion loops.
- **Trace Context Propagation**: Every child process execution inherits `HARNESS_BRIDGE_TRACE_ID` set to `session_id` and `HARNESS_BRIDGE_HOP_COUNT` incremented by 1.
- **Session Identity & Turn Continuity**: Tasks without a `session_id` are automatically assigned a unique UUIDv4. Existing sessions increment `turn_count` and mark `task.is_resume = True`.
- **Workspace Isolation Invariant**: `worktree_path` is exclusively tracked and populated when `task.workspace_mode == "worktree"`.
- **Diff Generation Guarantee**: Git diff extraction is only executed in `worktree` workspace mode, normalizing blank diffs to `None`.

## Side Effects
- Spawns external CLI agent processes via harness drivers (`claude`, `agy`).
- Creates and deletes filesystem directories and git worktree branches under `.worktrees/<session_id>` via `WorkspaceManager`.
- Updates in-memory session registry (`self.sessions`) across session lifecycles.
- Passes injected tracing environment variables to child subprocess execution environments.

## Verification
- Run: `pytest tests/test_session.py`
