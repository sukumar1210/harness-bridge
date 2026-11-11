from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkspaceMode = Literal["inherit", "worktree"]
SessionStatus = Literal["running", "completed", "failed", "timeout"]


class TaskSpec(BaseModel):
    harness: str
    prompt: str
    session_id: str | None = None
    workspace_mode: WorkspaceMode = "worktree"
    timeout_seconds: int = 300
    hop_count: int = 0
    max_hops: int = 10
    repo_root: str | None = None


class TaskResult(BaseModel):
    session_id: str
    harness: str
    status: SessionStatus
    output: str
    diff: str | None = None
    exit_code: int = 0
    duration_seconds: float = 0.0


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
