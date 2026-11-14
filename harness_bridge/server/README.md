# MCP Server (`harness_bridge.server`)

## Overview
The `harness_bridge.server` module implements the Model Context Protocol (MCP) server for Harness Bridge. It exposes standard FastMCP tools over standard I/O (`stdio`) that enable client AI coding harnesses (such as Claude Code, Antigravity CLI, or Cursor) to query available harnesses, dispatch isolated execution tasks, inspect active session state, apply git diffs from worktree sandboxes, and terminate sessions.

## Interface
- `mcp_app`: The root `MCPServer` instance managing MCP protocol compliance, tool registration, and stdio JSON-RPC message dispatch.
- `bridge_list_harnesses() -> list[dict[str, Any]]`: FastMCP tool enumerating registered agent harnesses (`claude`, `agy`), binary names, installation status on system `PATH`, and resolved binary paths.
- `bridge_dispatch_task(harness: str, prompt: str, session_id: str | None = None, workspace_mode: str = "inherit", timeout_seconds: int = 300, repo_root: str | None = None) -> dict[str, Any]`: FastMCP tool dispatching dev work, code reviews, or architectural exploration to a target AI harness CLI directly within the repository (default) or an isolated git worktree sandbox, returning a serialized `TaskResult`.
- `bridge_apply_diff(session_id: str, repo_root: str | None = None) -> dict[str, Any]`: FastMCP tool applying staged git diffs produced by a sandboxed session worktree branch into the primary repository tree.
- `bridge_get_session(session_id: str) -> dict[str, Any]`: FastMCP tool returning lifecycle tracking details (`SessionInfo`) for an active or historical session.
- `bridge_close_session(session_id: str, repo_root: str | None = None, cleanup_worktree: bool = True) -> dict[str, Any]`: FastMCP tool closing a session and optionally pruning its ephemeral worktree directory from disk.
- `run_server() -> None`: Asynchronous entrypoint configuring logging and launching the stdio JSON-RPC transport loop.

## Invariants
- **Stdio JSON-RPC Framing**: `stdout` is exclusively dedicated to valid JSON-RPC 2.0 protocol packets. No application logs, prints, or diagnostics may write to `stdout`.
- **Stderr Logging Isolation**: All diagnostic loggers and Rich console instances are explicitly bound to `stderr` (`stream=sys.stderr`, `Console(stderr=True)`) to eliminate transport framing corruption.
- **Distributed Loop Detection**: Integrates with `SessionManager` to propagate `HARNESS_BRIDGE_TRACE_ID` and enforce depth limits via `HARNESS_BRIDGE_HOP_COUNT`, raising `MaxHopsExceededError` if recursion depth reaches `max_hops`.
- **Workspace Sandboxing Integrity**: Worktree mode tasks operate strictly within `.worktrees/<session_id>` branches until explicitly merged via `bridge_apply_diff`, protecting the main branch from unreviewed concurrent edits.

## Side Effects
- Spawns headless child subprocesses for target harness CLI tools (`claude`, `agy`) and git commands.
- Mutates repository workspace trees by creating and removing git worktree directories (`.worktrees/<session_id>`).
- Applies git patches directly into the repository root when `bridge_apply_diff` is invoked.
- Injects distributed tracing environment variables (`HARNESS_BRIDGE_TRACE_ID`, `HARNESS_BRIDGE_HOP_COUNT`) into worker child processes.
- Writes structured operational logs and error messages to `sys.stderr``.

## Verification
- Run: `pytest tests/test_mcp_server.py`
