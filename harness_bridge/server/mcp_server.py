from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from rich.console import Console

from harness_bridge import __version__
from harness_bridge.core.types import SessionInfo, TaskSpec, WorkspaceMode
from harness_bridge.drivers.registry import list_all_harness_info
from harness_bridge.session.manager import SessionManager

# Ensure logging strictly uses sys.stderr to avoid polluting JSON-RPC transport on stdout
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("harness-bridge.server")
err_console = Console(stderr=True)

mcp_app = MCPServer(
    name="harness-bridge",
    version=__version__,
    description="Multi-harness inter-agent communication proxy and task execution server",
)

_session_manager = SessionManager()


@mcp_app.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
async def bridge_list_harnesses() -> list[dict[str, Any]]:
    """List all registered agent harnesses, their binary names, and installation status on system PATH."""
    infos = list_all_harness_info()
    return [info.model_dump() for info in infos]


@mcp_app.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
async def bridge_dispatch_task(
    harness: str,
    prompt: str,
    session_id: str | None = None,
    workspace_mode: str = "inherit",
    timeout_seconds: int = 300,
    repo_root: str | None = None,
    detach: bool = False,
) -> dict[str, Any]:
    """Dispatch a coding task or conversational turn to a target AI agent harness (e.g. 'claude' or 'agy').
    Use this tool to delegate dev work (feature implementation, bug fixes, refactoring), code and security reviews, or technical exploration and architectural prototyping to another agent.

    Args:
        harness: Target harness name ('claude', 'agy', or 'antigravity').
        prompt: Task instructions or follow-up prompt.
        session_id: Optional existing session ID for conversational resumption.
        workspace_mode: Workspace isolation mode. Defaults to 'inherit' (executes directly in the same repository and directory).
            Set to 'worktree' when delegating risky refactors, speculative implementations, parallel experiments, or tasks requiring an isolated branch diff review before applying. When using 'worktree', always review the resulting diff, apply it via bridge_apply_diff if approved, and clean up the temporary worktree when done using bridge_close_session(session_id, cleanup_worktree=True).
        timeout_seconds: Execution timeout in seconds (default: 300).
        repo_root: Path to target git repository (defaults to current directory).
        detach: If True, dispatches the task asynchronously in the background and returns the session_id immediately to prevent client timeouts on long turns. Poll or retrieve output via bridge_get_session.
    """
    mode: WorkspaceMode = "worktree" if workspace_mode == "worktree" else "inherit"
    resolved_session_id = session_id or str(uuid.uuid4())

    spec = TaskSpec(
        harness=harness,
        prompt=prompt,
        session_id=resolved_session_id,
        workspace_mode=mode,
        timeout_seconds=timeout_seconds,
        repo_root=repo_root,
        detach=detach,
    )

    if detach:
        # Pre-register session in memory and disk immediately with status 'running'
        init_session = _session_manager.get_session(resolved_session_id)
        if not init_session:
            init_session = SessionInfo(
                session_id=resolved_session_id,
                harness=harness,
                workspace_mode=mode,
                turn_count=1,
                created_at=time.time(),
                status="running",
            )
            _session_manager.sessions[resolved_session_id] = init_session
            _session_manager._save_session(init_session)

        # Launch background task execution
        asyncio.create_task(_session_manager.execute_task(spec))
        return {
            "session_id": resolved_session_id,
            "harness": harness,
            "status": "running",
            "output": f"Task dispatched in background to {harness}. Use bridge_get_session('{resolved_session_id}') to inspect status and output.",
            "diff": None,
            "exit_code": 0,
            "duration_seconds": 0.0,
        }

    result = await _session_manager.execute_task(spec)
    return result.model_dump()


@mcp_app.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
async def bridge_cancel_session(session_id: str) -> dict[str, Any]:
    """Cancel an active or running task session and terminate its subprocess group.

    Args:
        session_id: Session ID to cancel.
    """
    cancelled = await _session_manager.cancel_session(session_id)
    return {"session_id": session_id, "cancelled": cancelled}


@mcp_app.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
async def bridge_apply_diff(
    session_id: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Apply the code changes generated by a worker in an isolated git worktree branch into the main repository.
    After applying, call bridge_close_session(session_id, cleanup_worktree=True) to clean up the temporary worktree.

    Args:
        session_id: Session ID whose worktree branch should be applied.
        repo_root: Path to the target git repository (defaults to current directory).
    """
    root_path = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    result = await _session_manager.workspace_manager.apply_diff(root_path, session_id)
    return result.model_dump()


@mcp_app.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
async def bridge_get_session(session_id: str) -> dict[str, Any]:
    """Retrieve tracking details, output, diff, and token usage for an active or past session.

    Args:
        session_id: Session ID to inspect.
    """
    session = _session_manager.get_session(session_id)
    if not session:
        return {"error": f"Session '{session_id}' not found"}

    data = session.model_dump()
    if session.last_turn_result:
        data["output"] = session.last_turn_result.output
        data["diff"] = session.last_turn_result.diff
        data["exit_code"] = session.last_turn_result.exit_code
        data["duration_seconds"] = session.last_turn_result.duration_seconds
        data["usage"] = (
            session.last_turn_result.usage.model_dump() if session.last_turn_result.usage else None
        )
        data["num_turns"] = session.last_turn_result.num_turns
    else:
        data["output"] = ""
        data["diff"] = None
        data["exit_code"] = 0
        data["duration_seconds"] = 0.0
        data["usage"] = None
        data["num_turns"] = None

    return data


@mcp_app.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
async def bridge_close_session(
    session_id: str,
    repo_root: str | None = None,
    cleanup_worktree: bool = True,
) -> dict[str, Any]:
    """Close a session and clean up temporary worktrees.

    Args:
        session_id: Session ID to terminate.
        repo_root: Path to target repository.
        cleanup_worktree: Whether to remove the worktree folder on disk (default: True).
    """
    root_path = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    closed = await _session_manager.close_session(
        session_id, repo_root=root_path, cleanup_worktree=cleanup_worktree
    )
    return {"session_id": session_id, "closed": closed}


async def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the Model Context Protocol (MCP) server.

    Args:
        transport: MCP transport mechanism ('stdio', 'sse', or 'http').
        host: Host IP to bind for network transports (default: '127.0.0.1').
        port: Port to bind for network transports (default: 8000).
    """
    clean_transport = transport.lower().strip()
    if clean_transport == "stdio":
        logger.info("Starting Harness Bridge MCP stdio server v%s", __version__)
        await mcp_app.run_stdio_async()
    elif clean_transport == "sse":
        logger.info(
            "Starting Harness Bridge MCP SSE server v%s on http://%s:%d/sse",
            __version__,
            host,
            port,
        )
        await mcp_app.run_sse_async(host=host, port=port)
    elif clean_transport in ("http", "streamable-http"):
        logger.info(
            "Starting Harness Bridge MCP Streamable HTTP server v%s on http://%s:%d/mcp",
            __version__,
            host,
            port,
        )
        await mcp_app.run_streamable_http_async(host=host, port=port)
    else:
        raise ValueError(
            f"Unsupported MCP transport '{transport}'. Supported transports are: 'stdio', 'sse', 'http'."
        )
