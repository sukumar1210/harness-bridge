# Harness Bridge

[![CI](https://github.com/sukumar1210/harness-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/sukumar1210/harness-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**Harness Bridge** is a lightweight, harness-agnostic inter-agent proxy and Model Context Protocol (MCP) server for AI coding agents. It enables CLI-based harnesses (such as **Claude Code** and **Antigravity CLI**) to interoperate seamlessly, dispatching tasks, executing code in isolated sandboxes, and collaborating across distinct subscription accounts.

```
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator Harness (e.g., Claude Code, Antigravity, Codex)│
└──────────────────────────────┬──────────────────────────────┘
                               │ Stdio MCP Tool Calls
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Harness Bridge Core                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │  MCP Stdio Server (JSON-RPC 2.0 strictly on stdout)     │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │  Workspace Isolation Manager (Git Worktree / Inherit)   │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │  Session & Circuit Breaker Manager (Hop limits, timeouts│ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │  Harness Drivers: ClaudeCodeDriver & AntigravityDriver  │ │
│ └─────────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────────────┬───────────────┘
               │ Async Headless Subprocess    │ Async Headless Subprocess
               ▼                              ▼
┌──────────────────────────────┐ ┌─────────────────────────────┐
│ Worker Harness: Antigravity  │ │ Worker Harness: Claude Code │
│ (worktree: .worktrees/<id>)  │ │ (worktree: .worktrees/<id>) │
└──────────────────────────────┘ └─────────────────────────────┘
```

---

## Features

- **Standard Model Context Protocol (MCP) Server**: Exposes standard tools (`bridge_list_harnesses`, `bridge_dispatch_task`, `bridge_apply_diff`, `bridge_get_session`, `bridge_close_session`) that any MCP-compliant agent can invoke directly.
- **Dedicated Native Drivers**: Built-in, headless drivers for Claude Code (`claude`) and Antigravity CLI (`agy`) with conversational continuity across turns via native session resumption flags (`--resume` / `--conversation`).
- **Workspace Sandboxing via Git Worktrees**: Ephemeral git worktrees (`.worktrees/<session_id>`) prevent concurrent file clobbering. Review generated diffs safely before applying them with `bridge_apply_diff`.
- **Kernel Buffer & Protocol Deadlock Prevention**: Asynchronous execution via `proc.communicate()` wrapped with timeouts eliminates 64KB Linux pipe buffer deadlocks. All server logs route strictly to `stderr` to preserve clean JSON-RPC framing.
- **Distributed Loop Protection**: Injects `HARNESS_BRIDGE_TRACE_ID` and `HARNESS_BRIDGE_HOP_COUNT` into child processes to prevent recursive agent fork bombs.
- **Self-Updating**: Built-in `harness-bridge update` command syncs with GitHub Releases and updates in-place via pre-compiled `.whl` distribution assets.

---

## Quick Start & Installation

### Option 1: One-Line Installer (Recommended)

#### Linux / macOS:
```bash
curl -fsSL https://raw.githubusercontent.com/sukumar1210/harness-bridge/main/scripts/install.sh | bash
```

#### Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/sukumar1210/harness-bridge/main/scripts/install.ps1 | iex
```

### Option 2: Using `uv` or `pip`
```bash
# Clone the repository
git clone https://github.com/sukumar1210/harness-bridge.git
cd harness-bridge

# Install editable with dev dependencies
uv sync
```

---

## Connecting to Agent Harnesses

### Claude Code Registration
Register Harness Bridge as a local MCP server in Claude Code:
```bash
claude mcp add harness-bridge -- harness-bridge serve
```

### Antigravity CLI Registration
Register Harness Bridge in Antigravity:
```bash
agy mcp add harness-bridge harness-bridge serve
```

---

## CLI Usage

```bash
# List available harnesses on system PATH
harness-bridge list

# Check current version
harness-bridge version

# Check for updates from GitHub Releases
harness-bridge update --check

# Self-update to the latest release
harness-bridge update

# Run a one-shot task directly
harness-bridge run --target agy "Inspect README.md and explain the architecture"

# Start the MCP server manually
harness-bridge serve
```

---

## License

MIT © [Sukumar Rastogi](https://github.com/sukumar1210)
