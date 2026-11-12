# Harness Bridge Core (`harness_bridge.core`)

## Overview
The `harness_bridge.core` package provides foundational data models, domain exceptions, cross-platform subprocess execution utilities, automated harness setup/registration for Claude Code and Antigravity CLI, and GitHub release self-update facilities. It serves as the substrate for high-level drivers, workspace management, and MCP server transports.

## Interface

### Domain Exceptions (`exceptions.py`)
- `HarnessBridgeError(Exception)`: Base domain exception for Harness Bridge.
- `HarnessNotFoundError(HarnessBridgeError)`: Raised when a targeted harness CLI binary (`claude`, `agy`) is not found on the host system PATH.
- `SessionTimeoutError(HarnessBridgeError)`: Raised when a task or conversational turn execution exceeds the allotted timeout.
- `MaxHopsExceededError(HarnessBridgeError)`: Raised when distributed delegation recursion reaches the hop ceiling.
- `WorkspaceError(HarnessBridgeError)`: Raised when git worktree operations, status checks, or diff application fail.
- `UpdateError(HarnessBridgeError)`: Raised when self-update checking, wheel download, or pip upgrade invocation fails.

### Data Models & Schemas (`types.py`)
- `WorkspaceMode = Literal["inherit", "worktree"]`: Workspace isolation mode.
- `SessionStatus = Literal["running", "completed", "failed", "timeout"]`: Harness session execution state.
- `TaskSpec(BaseModel)`: Specification for a task dispatched to a harness (`harness`, `prompt`, `session_id`, `workspace_mode`, `timeout_seconds`, `hop_count`, `max_hops`, `repo_root`, `is_resume`).
- `TaskResult(BaseModel)`: Result payload returned by harness execution (`session_id`, `harness`, `status`, `output`, `diff`, `exit_code`, `duration_seconds`).
- `ApplyResult(BaseModel)`: Result of applying a worktree diff back into the target repository (`session_id`, `success`, `message`, `applied_files`).
- `HarnessInfo(BaseModel)`: Metadata describing an agent harness integration (`name`, `binary`, `installed`, `path`, `version`).
- `SessionInfo(BaseModel)`: Tracking metadata for an active or closed harness session (`session_id`, `harness`, `workspace_mode`, `worktree_path`, `turn_count`, `created_at`).

### Subprocess Management (`process.py`)
- `async def terminate_process_tree(proc: asyncio.subprocess.Process, timeout: float = 3.0) -> None`:
  Cross-platform process hierarchy termination (POSIX process groups via `os.killpg` with `SIGTERM`/`SIGKILL` escalation; Windows via `proc.terminate()`/`proc.kill()`).
- `async def run_command_safe(args: list[str], cwd: Path | str | None = None, env: dict[str, str] | None = None, timeout: float = 300.0) -> tuple[int, str, str]`:
  Asynchronously executes a command with `DEVNULL` stdin, piped stdout/stderr, process isolation (`process_group=0` on POSIX), and timeout-bound execution via `proc.communicate()` to prevent pipe buffer deadlocks. Returns `(exit_code, stdout, stderr)`.

### Harness Setup & Configuration (`setup.py`)
- `SetupStatus = Literal["configured", "already_configured", "not_installed", "failed"]`
- `HarnessSetupResult(dataclass)`: Result of harness registration (`harness`, `binary`, `status`, `message`).
- `def check_claude_configured_fast() -> bool`: Fast check for `harness-bridge` entry in `.mcp.json` or `~/.claude.json`.
- `def check_agy_configured_fast() -> bool`: Fast check for `harness-bridge` entry in Antigravity configuration files.
- `async def setup_claude(executable: str = "harness-bridge", force: bool = False) -> HarnessSetupResult`: Registers Harness Bridge MCP server in Claude Code.
- `async def setup_agy(executable: str = "harness-bridge", force: bool = False) -> HarnessSetupResult`: Registers Harness Bridge MCP server in Antigravity CLI.
- `async def setup_all_harnesses(executable: str | None = None, force: bool = False) -> list[HarnessSetupResult]`: Auto-detects and configures Harness Bridge across all installed harnesses.

### Self-Update Facilities (`updater.py`)
- `def parse_semver(v: str) -> tuple[int, ...]`: Parses semantic version strings into comparable integer tuples.
- `async def check_for_updates(repo: str = DEFAULT_REPO, force: bool = False) -> tuple[bool, str, str, str | None]`: Queries GitHub Releases API with 24-hour cache TTL at `~/.harness-bridge/update_cache.json`.
- `async def maybe_notify_update(repo: str = DEFAULT_REPO) -> None`: Passively prints update notification to stderr without interrupting stdout.
- `async def perform_update(repo: str = DEFAULT_REPO) -> bool`: Downloads latest `.whl` asset (or falls back to git release tag) and upgrades installation via `pip install --upgrade`.

## Invariants
- **Deadlock Immunity**: All subprocess executions bind stdin to `DEVNULL` and read via `proc.communicate()`, preventing 64KB Linux pipe deadlocks.
- **Process Group Cleanup**: POSIX subprocesses run in isolated process groups (`process_group=0`), guaranteeing complete termination of child processes on timeout.
- **Graceful Termination Escalation**: Unresponsive processes receive `SIGTERM`, followed by `SIGKILL` if still running after the timeout period.
- **Fail-Safe Fast Checks**: Fast configuration inspection functions suppress all file read and JSON parse errors, returning `False` safely.
- **Idempotent Harness Setup**: Harness setup commands inspect existing configuration files before running CLI registration to prevent duplicate entries.
- **Cache Interval Enforcement**: Update checks enforce a 24-hour cache TTL unless `force=True`.
- **Stdio Stream Isolation**: All update messages and logs route strictly to `stderr`, preserving `stdout` for clean MCP JSON-RPC protocol transport.

## Side Effects
- **Subprocess Execution**: Spawns system processes (`claude`, `agy`, `pip`, and shell binaries) via `asyncio.create_subprocess_exec`.
- **Process Signaling**: Sends `SIGTERM` and `SIGKILL` signals to process groups on POSIX systems.
- **Filesystem Writes**:
  - Creates `~/.harness-bridge/` and writes `~/.harness-bridge/update_cache.json`.
  - Creates temporary directories and writes downloaded `.whl` files during self-updates.
  - Modifies Claude (`.mcp.json`, `~/.claude.json`) and Antigravity (`mcp_config.json`) configuration files during setup.
- **Network Requests**:
  - Issues HTTPS GET requests to GitHub Releases API (`https://api.github.com/repos/{repo}/releases/latest`).
  - Downloads wheel assets over HTTPS.

## Verification
- Run: `pytest tests/test_setup.py tests/test_updater.py`
