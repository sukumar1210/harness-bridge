# CLI Interface (`harness_bridge.cli`)

## Overview
The `harness_bridge.cli` package provides the unified command-line interface and MCP stdio entrypoint for **Harness Bridge**. Built on [Typer](https://typer.tiangolo.com/) and formatted with [Rich](https://rich.readthedocs.io/), it enables both automated agent interoperability (via `harness-bridge serve`) and interactive developer workflows (including task dispatching, harness discovery, self-testing, self-updating, and automated harness registration).

The package exports the central `typer.Typer` application instance `app`, registered as the `harness-bridge` console script in `pyproject.toml`.

## Interface

### Python Module Exports
- `app`: Central `typer.Typer` CLI instance (`harness_bridge.cli.main.app`), also exposed via `harness_bridge.cli.__all__`.

### CLI Commands and Options

- `main_callback(ctx: typer.Context)`:
  - Global pre-command hook.
  - Automatically initiates background non-blocking release checks unless running `serve`.

- `serve`:
  - Starts the Model Context Protocol (MCP) server listening on standard I/O (`stdio`).
  - Implements JSON-RPC 2.0 communication over stdin/stdout.
  - Handles `KeyboardInterrupt` cleanly with user notice on stderr.

- `list`:
  - Discovers installed harness binaries across system `PATH` using `list_all_harness_info()`.
  - Displays a Rich table containing Harness Name, CLI Binary, Status (`✓ Installed` or `✗ Not Found`), and Resolved Path.

- `version`:
  - Prints Harness Bridge version, Python interpreter version/executable path, and host operating system/platform architecture.

- `update`:
  - Checks for or installs self-updates from GitHub releases.
  - Options:
    - `-c`, `--check` (flag, default: `False`): Check for newer releases without downloading or installing.
    - `-r`, `--repo` (string, default: `"sukumar1210/harness-bridge"`): Target GitHub repository identifier.

- `run <prompt>`:
  - Dispatches a prompt or coding task to a target harness.
  - Arguments:
    - `prompt` (argument, required): Prompt string or task instructions.
  - Options:
    - `-t`, `--target` (string, required): Target harness identifier (`claude`, `agy`, etc.).
    - `-w`, `--workspace` (string, default: `"worktree"`): Isolation mode (`"worktree"` for isolated git branch or `"inherit"` for in-place edits).
    - `-s`, `--session-id` (string, optional): Existing session identifier to resume conversational state.
    - `--timeout` (integer, default: `300`): Maximum execution timeout in seconds.
    - `--repo-root` (path, optional): Path to repository root; defaults to current working directory.
  - Outputs a Rich panel summarizing session ID, execution status, elapsed duration, harness exit code, task output, and any isolated git diff.

- `test`:
  - Executes local self-diagnostics verifying driver discovery and confirming that the working directory is a valid git repository.

- `setup`:
  - One-shot registration helper that discovers supported agent harnesses and configures Harness Bridge as an MCP server.
  - Options:
    - `-e`, `--executable` (string, optional): Custom executable binary path or invocation command for `harness-bridge`.
    - `-f`, `--force` (flag, default: `False`): Overwrite or re-register existing MCP server configurations.
  - Displays a Rich table with registration results (`Configured`, `Already Registered`, `Not Installed`, or `Failed`).

## Invariants
- **Stdio Protocol Purity**: When invoking `serve`, background update notifications are disabled (`ctx.invoked_subcommand != "serve"`). All status logs and errors route strictly to `stderr`, guaranteeing that `stdout` remains reserved for valid MCP JSON-RPC protocol frames.
- **Fail-Safe Update Polling**: Exceptions thrown during passive update checks are caught and discarded silently (`except Exception: pass`), ensuring offline and network-restricted environments never fail CLI invocations.
- **Predictable Exit Codes**: Failed self-updates cleanly raise `typer.Exit(code=1)`. Subcommand execution failures within spawned harnesses are captured and reported without crashing the CLI wrapper process.
- **Repository Path Defaults**: When `--repo-root` is omitted, the CLI automatically resolves the current working directory to an absolute path (`Path.cwd().resolve()`).

## Side Effects
- **Process Spawning**: Dispatches child CLI subprocesses asynchronously for harnesses (`claude`, `agy`) with inherited environment variables plus bridge tracing identifiers (`HARNESS_BRIDGE_TRACE_ID`, `HARNESS_BRIDGE_HOP_COUNT`).
- **Filesystem Mutations**:
  - `run` in `worktree` mode creates temporary git worktrees (`.worktrees/<session_id>`) in the host repository.
  - `setup` reads and modifies harness MCP configuration files in user directories (e.g., `~/.claude.json` or Antigravity configuration paths).
  - `update` downloads release wheel files and executes package installations in the current Python environment.
- **Network Requests**: Outbound HTTPS requests to `api.github.com` during update checks and release installations.
- **Terminal Rendering**: Outputs ANSI-colored text, tables, status spinners, and panels to stdout/stderr.

## Verification
- Verify CLI entrypoint and help outputs:
  - `harness-bridge --help`
  - `python -m harness_bridge.cli.main --help`
- Verify individual command schemas:
  - `harness-bridge serve --help`
  - `harness-bridge list --help`
  - `harness-bridge run --help`
  - `harness-bridge setup --help`
  - `harness-bridge test --help`
  - `harness-bridge update --help`
  - `harness-bridge version --help`
- Run local self-diagnostics:
  - `harness-bridge test`
