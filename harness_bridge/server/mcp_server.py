from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from rich.console import Console
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from harness_bridge import __version__
from harness_bridge.core.types import (
    SessionInfo,
    TaskResult,
    TaskSpec,
    WorkspaceMode,
)
from harness_bridge.drivers.registry import get_driver, list_all_harness_info
from harness_bridge.relay.bus import RelayBus
from harness_bridge.relay.embedded import EmbeddedWorker
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
_relay_bus = RelayBus()
_embedded_worker: EmbeddedWorker | None = None


def is_harness_installed(harness: str) -> bool:
    """Check if the harness executable exists on PATH."""
    try:
        driver = get_driver(harness)
        return driver.resolve_binary() is not None
    except Exception:
        return False


def verify_token(request: Request) -> bool:
    """Verify bearer token if HARNESS_BRIDGE_TOKEN is configured in environment."""
    expected = os.environ.get("HARNESS_BRIDGE_TOKEN")
    if not expected:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() == expected
    return request.query_params.get("token") == expected


def create_worker_routes(relay_bus: RelayBus) -> list[Route]:
    """Create Starlette routes for worker SSE subscription and REST task execution lifecycle."""

    async def worker_events_endpoint(request: Request) -> Response:
        if not verify_token(request):
            return JSONResponse(
                {"error": "Unauthorized: invalid HARNESS_BRIDGE_TOKEN"}, status_code=401
            )

        worker_id = request.query_params.get("worker_id") or f"worker-{uuid.uuid4().hex[:8]}"
        harnesses_raw = request.query_params.get("harnesses", "")
        harnesses = [h.strip() for h in harnesses_raw.split(",") if h.strip()]
        device_name = request.query_params.get("device")

        async def sse_stream():
            try:
                async for event in relay_bus.subscribe_worker(
                    worker_id=worker_id,
                    harnesses=harnesses,
                    device_name=device_name,
                ):
                    event_type = event.get("event", "message")
                    if event_type == "ping":
                        yield b": ping\n\n"
                    else:
                        data_json = json.dumps(event)
                        yield f"event: {event_type}\ndata: {data_json}\n\n".encode("utf-8")
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def list_workers_endpoint(request: Request) -> Response:
        if not verify_token(request):
            return JSONResponse(
                {"error": "Unauthorized: invalid HARNESS_BRIDGE_TOKEN"}, status_code=401
            )
        workers = relay_bus.store.list_active_workers()
        return JSONResponse([w.model_dump() for w in workers])

    async def task_ack_endpoint(request: Request) -> Response:
        if not verify_token(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        task_id = request.path_params["task_id"]
        body = await request.json()
        worker_id = body.get("worker_id", "")
        ok = relay_bus.ack_task(task_id, worker_id)
        if ok:
            return JSONResponse({"ok": True, "task_id": task_id, "worker_id": worker_id})
        return JSONResponse(
            {"ok": False, "error": "Task already claimed or expired"}, status_code=409
        )

    async def task_heartbeat_endpoint(request: Request) -> Response:
        if not verify_token(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        task_id = request.path_params["task_id"]
        body = await request.json()
        worker_id = body.get("worker_id", "")
        ok = relay_bus.heartbeat_task(task_id, worker_id)
        return JSONResponse({"ok": ok, "task_id": task_id})

    async def task_complete_endpoint(request: Request) -> Response:
        if not verify_token(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        task_id = request.path_params["task_id"]
        body = await request.json()
        worker_id = body.get("worker_id", "")
        result_data = body.get("result", {})
        try:
            result = TaskResult.model_validate(result_data)
            ok = relay_bus.complete_task(task_id, worker_id, result)
            return JSONResponse({"ok": ok, "task_id": task_id})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def task_fail_endpoint(request: Request) -> Response:
        if not verify_token(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        task_id = request.path_params["task_id"]
        body = await request.json()
        worker_id = body.get("worker_id", "")
        error = body.get("error", "Unknown error")
        ok = relay_bus.fail_task(task_id, worker_id, error)
        return JSONResponse({"ok": ok, "task_id": task_id})

    return [
        Route("/api/v1/workers/events", endpoint=worker_events_endpoint, methods=["GET"]),
        Route("/api/v1/workers", endpoint=list_workers_endpoint, methods=["GET"]),
        Route("/api/v1/tasks/{task_id}/ack", endpoint=task_ack_endpoint, methods=["POST"]),
        Route(
            "/api/v1/tasks/{task_id}/heartbeat", endpoint=task_heartbeat_endpoint, methods=["POST"]
        ),
        Route(
            "/api/v1/tasks/{task_id}/complete", endpoint=task_complete_endpoint, methods=["POST"]
        ),
        Route("/api/v1/tasks/{task_id}/fail", endpoint=task_fail_endpoint, methods=["POST"]),
    ]


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
    task_id = str(uuid.uuid4())

    spec = TaskSpec(
        harness=harness,
        prompt=prompt,
        session_id=resolved_session_id,
        task_id=task_id,
        workspace_mode=mode,
        timeout_seconds=timeout_seconds,
        repo_root=repo_root,
        detach=detach,
    )

    use_relay = _relay_bus.has_active_workers(harness)

    if detach:
        if use_relay:
            await _relay_bus.submit_task(spec)
        else:
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
            "task_id": task_id,
            "session_id": resolved_session_id,
            "harness": harness,
            "status": "running",
            "output": f"Task dispatched in background to {harness}. Use bridge_get_session('{resolved_session_id}') to inspect status and output.",
            "diff": None,
            "exit_code": 0,
            "duration_seconds": 0.0,
        }

    if use_relay:
        await _relay_bus.submit_task(spec)
        result = await _relay_bus.wait_for_task_completion(task_id, timeout=timeout_seconds)
        return result.model_dump()

    result = await _session_manager.execute_task(spec)
    result.task_id = task_id
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
    latest_task = _relay_bus.store.get_latest_task_for_session(session_id)
    if latest_task and latest_task.status not in ("completed", "failed"):
        _relay_bus.cancel_task(latest_task.task_id)
        cancelled = True
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
    latest_task = _relay_bus.store.get_latest_task_for_session(session_id)
    if latest_task:
        if latest_task.result:
            data = latest_task.result.model_dump()
            data["task_id"] = latest_task.task_id
            return data
        elif latest_task.status in ("pending", "offered", "assigned", "running"):
            return {
                "session_id": session_id,
                "task_id": latest_task.task_id,
                "harness": latest_task.harness,
                "status": "running",
                "output": f"Task is currently {latest_task.status}.",
                "diff": None,
                "exit_code": 0,
                "duration_seconds": max(0.0, time.time() - latest_task.created_at),
                "usage": None,
                "num_turns": None,
            }
        elif latest_task.status in ("failed", "timeout", "cancelled"):
            return {
                "session_id": session_id,
                "task_id": latest_task.task_id,
                "harness": latest_task.harness,
                "status": latest_task.status,
                "output": latest_task.error or f"Task ended with status {latest_task.status}",
                "diff": None,
                "exit_code": 1,
                "duration_seconds": max(0.0, latest_task.updated_at - latest_task.created_at),
                "usage": None,
                "num_turns": None,
            }

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
    enable_embedded_worker: bool = True,
) -> None:
    """Run the Model Context Protocol (MCP) server.

    Args:
        transport: MCP transport mechanism ('stdio', 'sse', 'http', or 'unified').
        host: Host IP to bind for network transports (default: '127.0.0.1').
        port: Port to bind for network transports (default: 8000).
        enable_embedded_worker: Auto-spawn in-process embedded worker for local harnesses.
    """
    global _embedded_worker
    await _relay_bus.start()

    if enable_embedded_worker:
        _embedded_worker = EmbeddedWorker(_relay_bus, _session_manager)
        await _embedded_worker.start()

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
    elif clean_transport in ("unified", "network"):
        import uvicorn
        from starlette.applications import Starlette

        logger.info(
            "Starting Harness Bridge Unified MCP server v%s on http://%s:%d (SSE: /sse, HTTP: /mcp & /sse)",
            __version__,
            host,
            port,
        )
        sse_app = mcp_app.sse_app()
        http_app = mcp_app._lowlevel_server.streamable_http_app(
            streamable_http_path="/mcp", host=host
        )
        http_endpoint = http_app.routes[0].endpoint

        worker_routes = create_worker_routes(_relay_bus)

        routes = worker_routes + [
            Route("/sse", endpoint=sse_app.routes[0].endpoint, methods=["GET", "HEAD"]),
            Route("/sse", endpoint=http_endpoint, methods=["POST"]),
            Route("/mcp", endpoint=http_endpoint),
            sse_app.routes[1],  # Mount('/messages')
        ]
        unified_app = Starlette(
            routes=routes,
            lifespan=http_app.router.lifespan_context,
        )
        config = uvicorn.Config(
            unified_app,
            host=host,
            port=port,
            log_level=mcp_app.settings.log_level.lower(),
        )
        server = uvicorn.Server(config)
        await server.serve()
    else:
        raise ValueError(
            f"Unsupported MCP transport '{transport}'. Supported transports are: 'stdio', 'sse', 'http', 'unified'."
        )
