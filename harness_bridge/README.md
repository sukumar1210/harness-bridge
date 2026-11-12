# Harness Bridge Python Subsystem (`harness_bridge`)

## Overview
The `harness_bridge` package is the core Python implementation of the Harness Bridge inter-agent proxy and Model Context Protocol (MCP) server. It groups the foundational subsystems responsible for CLI command parsing, headless AI harness subprocess orchestration, git worktree isolation, multi-turn session tracking, and stdio JSON-RPC tool dispatch.

## Subdirectories & Boundaries
- [CLI (`cli`)](./cli/README.md): Unified command-line interface (`harness-bridge`) and MCP stdio server launcher implemented with Typer and Rich.
- [Core (`core`)](./core/README.md): Foundational domain data models, exceptions, deadlock-immune asynchronous subprocess execution (`run_command_safe`), automated harness configuration, and self-update utilities.
- [Drivers (`drivers`)](./drivers/README.md): Headless CLI adapters and registry for target AI coding harnesses (Anthropic Claude Code and Google Antigravity CLI).
- [Server (`server`)](./server/README.md): FastMCP stdio server exposing JSON-RPC 2.0 tools for harness discovery, task execution, diff application, and session tracking.
- [Session (`session`)](./session/README.md): Multi-turn session lifecycle management, tracing header propagation, and distributed recursion circuit breakers (`HARNESS_BRIDGE_HOP_COUNT`).
- [Workspace (`workspace`)](./workspace/README.md): Sandboxed git worktree provisioning (`.worktrees/{session_id}`), unified diff extraction, and target repository patch application.
