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

## Subdirectories & System Boundaries
- [Python Subsystem (`harness_bridge`)](./harness_bridge/README.md): Core implementation including CLI, drivers, session management, workspace sandboxing, and FastMCP server.
  - [CLI (`harness_bridge/cli`)](./harness_bridge/cli/README.md): Typer/Rich command-line interface and MCP stdio server launcher.
  - [Core (`harness_bridge/core`)](./harness_bridge/core/README.md): Domain exceptions, schemas, async process runner, harness configuration, and self-updater.
  - [Drivers (`harness_bridge/drivers`)](./harness_bridge/drivers/README.md): Headless execution adapters and registry for Claude Code and Antigravity CLI.
  - [Server (`harness_bridge/server`)](./harness_bridge/server/README.md): FastMCP stdio server exposing JSON-RPC tools for agent discovery and dispatch.
  - [Session (`harness_bridge/session`)](./harness_bridge/session/README.md): Multi-turn conversational session lifecycle, tracing, and hop limit circuit breakers.
  - [Workspace (`harness_bridge/workspace`)](./harness_bridge/workspace/README.md): Ephemeral git worktree sandboxing, diff extraction, and patch application.
- [Bootstrap Scripts (`scripts`)](./scripts/README.md): Platform-native installation scripts (`install.sh`, `install.ps1`) for Unix and Windows.
- [Technical Design Specifications (`docs/designs`)](./docs/designs/SITEMAP.md): Canonical architectural RFCs and feature milestone specifications.

## Global Invariants
- **Stdio Transport Protocol Purity**: During `harness-bridge serve`, standard output (`stdout`) is strictly reserved for JSON-RPC 2.0 frames. All diagnostics, progress spinners, and log messages route strictly to `stderr`.
- **Subprocess Pipe Deadlock Immunity**: Cross-platform process execution in `run_command_safe` binds stdin to `DEVNULL` and reads output via `proc.communicate()`, eliminating 64KB OS pipe deadlocks.
- **Process Group Termination**: Child subprocesses are spawned in detached process groups (`process_group=0` on POSIX) and terminated recursively with `SIGTERM`/`SIGKILL` escalation on timeout.
- **Workspace Sandboxing Integrity**: Tasks executed under `worktree` isolation operate strictly within ephemeral `.worktrees/{session_id}` directories and dedicated `bridge/session-{session_id}` branches, never modifying the primary working tree until explicitly merged via `bridge_apply_diff`.
- **Distributed Delegation Recursion Ceiling**: Inter-agent delegation propagates `HARNESS_BRIDGE_TRACE_ID` and increments `HARNESS_BRIDGE_HOP_COUNT`, raising `MaxHopsExceededError` if recursion depth reaches `max_hops` (default: 10).

## Global Side Effects
- **Child Subprocess Execution**: Spawns headless external AI coding harness CLIs (`claude`, `agy`) and git processes.
- **Repository Worktree & Branch Mutation**: Creates and removes `.worktrees/{session_id}` directories and mutates local git branches (`bridge/session-*`).
- **Harness MCP Configuration Writes**: Reads and updates configuration files across user directories (`~/.claude.json`, `~/.gemini/antigravity-cli/mcp_config.json`, `~/.gemini/config/mcp_config.json`).
- **Network Egress**: Issues HTTPS requests to `api.github.com` for release checks and updates, downloading `.whl` assets when upgrading.

## System Verification
- Run: `pytest`

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

### Next Step: One-Shot Setup
Once installed, register Harness Bridge with all detected harnesses in one command:
```bash
harness-bridge setup
```

---

## Connecting to Agent Harnesses

### One-Shot Automatic Setup (Recommended)
Auto-detect all installed coding harnesses on your system PATH (`claude`, `agy`) and register Harness Bridge as an MCP server with a single command:
```bash
harness-bridge setup
```
Use `--force` to re-register or update existing configurations:
```bash
harness-bridge setup --force
```

---

### Manual Registration by Harness

Harness Bridge exposes a standard Model Context Protocol (MCP) server over standard I/O (`stdio`). You can also register it manually in any MCP-compliant harness or IDE:

### 1. Claude Code
Register Harness Bridge directly using the `claude` CLI:
```bash
claude mcp add harness-bridge -- harness-bridge serve
```

Alternatively, add it directly to your project or user configuration (`~/.claude.json`):
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "harness-bridge",
      "args": ["serve"]
    }
  }
}
```

### 2. Antigravity CLI (`agy`)
Register Harness Bridge using the `agy` CLI:
```bash
agy mcp add harness-bridge harness-bridge serve
```

Or configure it in your Antigravity MCP settings (`~/.gemini/antigravity-cli/mcp_config.json`):
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "harness-bridge",
      "args": ["serve"]
    }
  }
}
```

### 3. Cursor
In Cursor:
1. Navigate to **Cursor Settings** > **Features** > **MCP Servers**.
2. Click **+ Add New MCP Server**.
3. Fill in:
   - **Name**: `harness-bridge`
   - **Type**: `command`
   - **Command**: `harness-bridge serve` *(or `~/.local/bin/harness-bridge serve` if not in global PATH)*

### 4. Windsurf (Codeium Cascade)
Add the server configuration to `~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "harness-bridge",
      "args": ["serve"]
    }
  }
}
```

### 5. Claude Desktop
Add to your `claude_desktop_config.json` (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "harness-bridge",
      "args": ["serve"]
    }
  }
}
```

### 6. Generic MCP Clients / Zed / Goose
Any client supporting JSON-RPC stdio transport can connect to Harness Bridge:
* **Executable**: `harness-bridge` (or `$HOME/.local/bin/harness-bridge`)
* **Arguments**: `["serve"]`
* **Transport**: `stdio`

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

## Contributing

Contributions, issues, and feature requests are welcome!
- See [CONTRIBUTING.md](CONTRIBUTING.md) for local development setup, testing guidelines, and PR workflow.
- Please review our [Code of Conduct](CODE_OF_CONDUCT.md).
- To report security concerns, refer to [SECURITY.md](SECURITY.md).

---

## License

MIT © [Sukumar Rastogi](https://github.com/sukumar1210)
