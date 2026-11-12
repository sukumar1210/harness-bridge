# Harness Drivers (`harness_bridge.drivers`)

## Overview
The `harness_bridge.drivers` package implements harness-specific execution adapters and a centralized driver registry for external AI coding CLIs. It abstracts vendor-specific CLI flags, session continuity mechanisms, and headless execution protocols into a unified interface (`BaseDriver`), supporting Anthropic's Claude Code CLI (`claude`) and Google's Antigravity CLI (`agy`).

## Interface

### Classes
- `BaseDriver` (abstract): Abstract base class defining the execution interface and binary resolution for harness drivers.
  - `name: str` (abstract property): Normalized identifier of the harness (e.g., `'claude'`, `'agy'`).
  - `binary_name: str` (abstract property): Name of the CLI executable on system `PATH`.
  - `resolve_binary() -> Path | None`: Resolves the absolute path of the executable via `shutil.which`.
  - `is_installed() -> bool`: Returns `True` if the binary exists on system `PATH`.
  - `async run_turn(task: TaskSpec, cwd: Path, env: dict[str, str]) -> TaskResult` (abstract method): Executes a single headless conversational or coding turn.
- `ClaudeCodeDriver(BaseDriver)`: Driver implementation for Anthropic's Claude Code CLI (`claude`).
  - `name`: `"claude"`
  - `binary_name`: `"claude"`
  - `async run_turn(...) -> TaskResult`: Spawns `claude` with `-p <prompt> --output-format json --dangerously-skip-permissions` and optional `--resume <session_id>`.
- `AntigravityDriver(BaseDriver)`: Driver implementation for Google's Antigravity CLI (`agy`).
  - `name`: `"agy"`
  - `binary_name`: `"agy"`
  - `async run_turn(...) -> TaskResult`: Spawns `agy` with `-p <prompt> --output-format json --dangerously-skip-permissions` and optional `--conversation <session_id>`.

### Registry Functions
- `get_driver(name: str) -> BaseDriver`: Retrieves registered driver instance by normalized name or alias (case-insensitive, whitespace-trimmed). Raises `HarnessNotFoundError` if unrecognized.
- `list_unique_drivers() -> list[BaseDriver]`: Returns deduplicated list of unique driver singleton instances.
- `get_harness_info(driver: BaseDriver) -> HarnessInfo`: Probes driver installation status and binary path on system PATH.
- `list_all_harness_info() -> list[HarnessInfo]`: Returns status inspection records for all unique registered harness drivers.

## Invariants
- **Binary Precondition**: Harness binary must exist on system `PATH`; `run_turn()` raises `HarnessNotFoundError` before process invocation if unresolved.
- **Headless Non-Interactive Operation**: Drivers pass `--dangerously-skip-permissions` and `--output-format json` to ensure non-blocking, headless execution without TTY prompts.
- **Session Continuity Flags**:
  - `ClaudeCodeDriver` maps session resumption to `--resume <session_id>`.
  - `AntigravityDriver` maps session resumption to `--conversation <session_id>`.
- **Registry Deduplication & Aliasing**: `antigravity` aliases to `AntigravityDriver` (`name="agy"`). Registry queries are case-insensitive and stripped. `list_unique_drivers()` deduplicates drivers by canonical `driver.name`.
- **Output Parsing & Error Fallback**: Drivers attempt to parse structured JSON output (checking `result`, `text`, or `response` fields). On non-zero exit codes with empty stdout, `stderr` is captured into `TaskResult.output`.

## Side Effects
- **Subprocess Spawning**: Executes asynchronous headless CLI processes via `run_command_safe`, redirecting `stdin` to `DEVNULL` and capturing `stdout`/`stderr` through pipes.
- **Process Group Isolation**: Subprocesses are spawned in separate process groups on POSIX systems (`process_group=0`) and terminated recursively (`SIGTERM` / `SIGKILL`) on timeout.
- **System Inspection**: Probes the host OS filesystem and environment `PATH` via `shutil.which`.

## Verification
- Run: `pytest tests/test_drivers.py`
