from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WorkspaceMode = Literal["inherit", "worktree"]
SessionStatus = Literal["running", "completed", "failed", "timeout", "cancelled"]


class TokenUsage(BaseModel):
    """Token consumption and estimated cost statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None


class TaskSpec(BaseModel):
    harness: str
    prompt: str
    session_id: str | None = None
    workspace_mode: WorkspaceMode = "inherit"
    timeout_seconds: int = 300
    hop_count: int = 0
    max_hops: int = 10
    repo_root: str | None = None
    is_resume: bool = False
    harness_session_id: str | None = None
    detach: bool = False


class TaskResult(BaseModel):
    session_id: str
    harness: str
    status: SessionStatus
    output: str
    diff: str | None = None
    exit_code: int = 0
    duration_seconds: float = 0.0
    harness_session_id: str | None = None
    usage: TokenUsage | None = None
    num_turns: int | None = None
    driver_metadata: dict[str, Any] = Field(default_factory=dict)


class ApplyResult(BaseModel):
    session_id: str
    success: bool
    message: str
    applied_files: list[str] = Field(default_factory=list)


class HarnessInfo(BaseModel):
    name: str
    binary: str
    installed: bool
    path: str | None = None
    version: str | None = None


class SessionInfo(BaseModel):
    session_id: str
    harness: str
    workspace_mode: WorkspaceMode
    worktree_path: str | None = None
    turn_count: int = 0
    created_at: float = 0.0
    harness_session_id: str | None = None
    active_pid: int | None = None
    status: SessionStatus = "running"
    driver_metadata: dict[str, Any] = Field(default_factory=dict)
    last_turn_result: TaskResult | None = None
