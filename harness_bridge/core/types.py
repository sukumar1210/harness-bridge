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
    task_id: str | None = None
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
    task_id: str | None = None


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


TaskQueueStatus = Literal[
    "pending", "offered", "assigned", "running", "completed", "failed", "timeout", "cancelled"
]


class TaskRecord(BaseModel):
    task_id: str
    session_id: str
    harness: str
    prompt: str
    workspace_mode: WorkspaceMode = "inherit"
    repo_root: str | None = None
    timeout_seconds: int = 300
    detach: bool = False
    status: TaskQueueStatus = "pending"
    worker_id: str | None = None
    lease_expires_at: float | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    result: TaskResult | None = None
    error: str | None = None


class WorkerInfo(BaseModel):
    worker_id: str
    harnesses: list[str] = Field(default_factory=list)
    connected_at: float = 0.0
    last_seen_at: float = 0.0
    is_active: bool = True
    device_name: str | None = None


class TaskAckRequest(BaseModel):
    worker_id: str


class TaskHeartbeatRequest(BaseModel):
    worker_id: str


class TaskCompleteRequest(BaseModel):
    worker_id: str
    result: TaskResult


class TaskFailRequest(BaseModel):
    worker_id: str
    error: str
    exit_code: int = 1


BridgeMode = Literal["local", "bridge_link"]


class BridgeLinkConfig(BaseModel):
    """Bridge-Link operational configuration."""

    mode: BridgeMode = Field(
        default="local", description="Operational mode: 'local' or 'bridge_link'."
    )
    api_url: str = Field(
        default="https://link.harnessbridge.ai",
        description="Base URL of the remote Bridge-Link Control Plane.",
    )
    credentials_file: str = Field(
        default="~/.harness-bridge/credentials.json",
        description="Path to stored credentials JSON file.",
    )
    retry_max_attempts: int = Field(
        default=3, description="Maximum retry attempts on transient network drops."
    )
    retry_backoff_base: float = Field(default=0.5, description="Initial retry delay in seconds.")


class StoredCredentials(BaseModel):
    """Credentials payload saved in credentials.json."""

    access_token: str
    account_id: str
    tenant_id: str
    expires_at: float
    device_name: str | None = None
