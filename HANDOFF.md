# SESSION HANDOFF: Harness Bridge Implementation

> [!IMPORTANT]
> **Instructions for the Incoming Agent Session:**
> 1. Read this handoff document completely to ingest the full architectural context, design decisions, and project state.
> 2. Complete the remaining implementation steps detailed below (scripts, CI workflows, and test suite).
> 3. Run the automated tests (`uv run pytest -v tests/`).
> 4. Initialize the git commit and publish the repository to GitHub: `gh repo create harness-bridge --public --source=. --remote=origin --push`.
> 5. **Once finished and verified, delete this `HANDOFF.md` file from the repository.**

---

## 1. Project Background & Executive Overview

**Harness Bridge** is an open-source, harness-agnostic inter-agent proxy and Model Context Protocol (MCP) server designed to enable different AI coding harnesses—specifically **Claude Code** and **Antigravity CLI** (`agy`)—to communicate, delegate tasks, execute code in isolated sandboxes, and collaborate across separate subscription accounts simultaneously.

- **Author / GitHub User:** Sukumar Rastogi (`sukumar1210`)
- **Target Repository:** `sukumar1210/harness-bridge` (Public)
- **Local Directory:** `/home/sukumar/sources/harness-bridge` (symlinked to `/srv/sources/harness-bridge`)
- **Tech Stack:** Python 3.13, `uv`, `mcp` (v2.x `mcp.server.mcpserver`), `typer`, `pydantic` v2, `rich`, `httpx`, `pytest`, `pytest-asyncio`, `hatchling`.

---

## 2. Resolved Architectural Decisions (From Brainstorm, Interview & Goldfish Review)

During ideation, user interview, and rigorous 5-stage Goldfish review (Zoom Out, Comprehension, Critic, Intermediate Zoom Out, Implementation Readiness), the following architectural anchors were finalized:

1. **Primary Protocol (Stdio MCP Server)**:
   - Exposes standard tools: `bridge_list_harnesses`, `bridge_dispatch_task`, `bridge_apply_diff`, `bridge_get_session`, `bridge_close_session`.
   - Any MCP-compliant harness (Claude Code via `claude mcp add`, Antigravity via `agy mcp add`) can immediately delegate tasks without custom harness plugins.

2. **Stateless Headless Execution with Native Session Resumption**:
   - Rather than attempting fragile, unverified bidirectional NDJSON streaming pipes (`--input-format stream-json --output-format stream-json`), each task turn executes as an asynchronous, self-contained headless subprocess:
     - Claude Code: `claude -p "<prompt>" --output-format json --dangerously-skip-permissions [--resume <session_id>]`
     - Antigravity CLI: `agy -p "<prompt>" --output-format json --dangerously-skip-permissions [--conversation <session_id>]`
   - Conversational continuity is preserved across turns via native session resumption flags, eliminating background daemon pipes and zombie processes.

3. **Workspace Isolation via Git Worktrees**:
   - Default is `worktree` isolation: when a worker task is dispatched, the bridge creates an ephemeral git worktree at `.worktrees/<session_id>` on branch `bridge/session-<session_id>`.
   - Worker runs with automated bypass permissions inside the worktree without polluting the main working copy.
   - Newly created and untracked files are staged via `git add -N .` before running `git diff HEAD`, ensuring complete diff extraction.
   - The orchestrator or user can review the diff and apply changes into the working copy using the `bridge_apply_diff(session_id)` MCP tool.
   - Direct in-place editing (`inherit` mode) is supported for read-only or sequential single-agent handoffs.

4. **Kernel Buffer & Protocol Deadlock Prevention**:
   - On Linux, kernel pipe buffers are 64KB. All subprocess executions use `asyncio.create_subprocess_exec` paired with `await proc.communicate()` wrapped with `asyncio.timeout()` to eliminate pipe buffer deadlocks.
   - MCP stdio transport requires `sys.stdout` to be strictly clean JSON-RPC 2.0 messages. All logging is routed to `sys.stderr` (`logging.basicConfig(stream=sys.stderr)`), Rich consoles use `stderr=True`, and child subprocesses redirect standard descriptors (`stdout=PIPE, stderr=PIPE`).

5. **Cross-Platform Process Group Lifecycle**:
   - Launches child processes with `process_group=0` on POSIX.
   - `terminate_process_tree` issues `SIGTERM` to the process group, waits a 3-second grace period, and escalates to `SIGKILL`. On Windows, uses native `terminate()` / `kill()`.
   - Startup hook executes `git worktree prune --expire now` to clear stale locks left by crashed sessions.

6. **Distributed Loop Protection**:
   - Child processes inherit `HARNESS_BRIDGE_TRACE_ID = <session_id>` and `HARNESS_BRIDGE_HOP_COUNT = <count + 1>`.
   - Execution halts if `hop_count >= max_hops` (default 10) to prevent recursive agent fork bombs.

7. **Installation, Releases & Update Strategy**:
   - One-line installer scripts (`scripts/install.sh` for POSIX, `scripts/install.ps1` for Windows PowerShell) create a dedicated virtualenv at `~/.harness-bridge/venv` and symlink the binary to `~/.local/bin/harness-bridge`.
   - Automated GitHub Actions release pipeline (`.github/workflows/release.yml`) triggers on `v*` tags, tests across Linux/macOS/Windows, builds distribution wheels, and attaches them to GitHub Releases.
   - Built-in `harness-bridge update` command downloads pre-compiled `.whl` assets directly from GitHub Releases and updates the venv in-place.
   - Passive 24-hour background update check prints a one-line update notice strictly to `sys.stderr` on CLI startup.

---

## 3. Current Project State

The following components are already written, configured, and synchronized in `/home/sukumar/sources/harness-bridge`:

- `pyproject.toml` (Configured with `hatchling`, dependencies `mcp>=1.0.0`, `typer>=0.12.0`, `pydantic>=2.7.0`, `rich>=13.7.0`, `httpx>=0.27.0`, dev dependencies `pytest`, `pytest-asyncio`).
- `uv.lock` (Deterministic lockfile generated and synced via `uv sync`).
- `.gitignore` (Configured for Python, venvs, `.worktrees/`, `.harness-bridge/`, cache files).
- `README.md` (Architecture diagrams, installation instructions, MCP setup guides for Claude Code & Antigravity).
- `harness_bridge/__init__.py` (`__version__ = "0.1.0"`).
- `harness_bridge/core/`:
  - `types.py` (`TaskSpec`, `TaskResult`, `ApplyResult`, `HarnessInfo`, `SessionInfo`, `WorkspaceMode`, `SessionStatus`).
  - `exceptions.py` (`HarnessBridgeError`, `HarnessNotFoundError`, `SessionTimeoutError`, `MaxHopsExceededError`, `WorkspaceError`, `UpdateError`).
  - `process.py` (`terminate_process_tree`, `run_command_safe` with `proc.communicate()` buffer safety).
  - `updater.py` (`check_for_updates`, `maybe_notify_update`, `perform_update`).
  - `__init__.py`.
- `harness_bridge/workspace/`:
  - `manager.py` (`WorkspaceManager` implementing `prepare_workspace`, `extract_diff`, `apply_diff`, `cleanup_workspace`).
  - `__init__.py`.
- `harness_bridge/drivers/`:
  - `base.py` (`BaseDriver` abstract base class).
  - `claude.py` (`ClaudeCodeDriver` executing `claude -p` with `--resume`).
  - `antigravity.py` (`AntigravityDriver` executing `agy -p` with `--conversation`).
  - `registry.py` (`get_driver`, `list_unique_drivers`, `get_harness_info`, `list_all_harness_info`).
  - `__init__.py`.
- `harness_bridge/session/`:
  - `manager.py` (`SessionManager` coordinating workspace, hop tracking, trace injection, and turn dispatch).
  - `__init__.py`.
- `harness_bridge/server/`:
  - `mcp_server.py` (Stdio MCP server with mcp 2.x `MCPServer`, logging to `sys.stderr`, tools: `bridge_list_harnesses`, `bridge_dispatch_task`, `bridge_apply_diff`, `bridge_get_session`, `bridge_close_session`).
  - `__init__.py`.
- `harness_bridge/cli/`:
  - `main.py` (Typer CLI with commands: `serve`, `list`, `version`, `update`, `run`, `test`).

---

## 4. Remaining Implementation Steps

The incoming session must complete the following items:

### Step 4.1: Create `harness_bridge/cli/__init__.py`
```python
"""CLI interface package."""

from harness_bridge.cli.main import app

__all__ = ["app"]
```

### Step 4.2: Create Standalone Installer Scripts
1. **`scripts/install.sh`**:
```bash
#!/usr/bin/env bash
set -euo pipefail

REPO="sukumar1210/harness-bridge"
INSTALL_DIR="${HOME}/.harness-bridge"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"

echo "=== Installing Harness Bridge ==="

# Ensure Python 3.11+
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not installed." >&2
    exit 1
fi

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment in ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

echo "Fetching latest release information from GitHub..."
RELEASE_JSON=$(curl -sSL "https://api.github.com/repos/${REPO}/releases/latest" || true)
WHEEL_URL=$(echo "${RELEASE_JSON}" | grep -o 'https://[^"]*harness_bridge[^"]*\.whl' | head -n 1 || true)

if [ -n "${WHEEL_URL}" ]; then
    echo "Downloading wheel from ${WHEEL_URL}..."
    TMP_WHL=$(mktemp --suffix=.whl)
    curl -sSL "${WHEEL_URL}" -o "${TMP_WHL}"
    "${VENV_DIR}/bin/pip" install --upgrade --quiet "${TMP_WHL}"
    rm -f "${TMP_WHL}"
else
    echo "Installing latest package from repository..."
    "${VENV_DIR}/bin/pip" install --upgrade --quiet "git+https://github.com/${REPO}.git"
fi

ln -sf "${VENV_DIR}/bin/harness-bridge" "${BIN_DIR}/harness-bridge"

echo "=== Harness Bridge installed successfully to ${BIN_DIR}/harness-bridge ==="
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo "Note: Please ensure ${BIN_DIR} is in your PATH (e.g. export PATH=\"\$HOME/.local/bin:\$PATH\")."
fi
```
Make executable: `chmod +x scripts/install.sh`.

2. **`scripts/install.ps1`**:
```powershell
$ErrorActionPreference = "Stop"
$Repo = "sukumar1210/harness-bridge"
$InstallDir = Join-Path $HOME ".harness-bridge"
$VenvDir = Join-Path $InstallDir "venv"
$BinDir = Join-Path $HOME ".local\bin"

Write-Host "=== Installing Harness Bridge ===" -ForegroundColor Cyan

if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null }
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir -Force | Out-Null }

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment in $VenvDir..."
    python -m venv $VenvDir
}

$Pip = Join-Path $VenvDir "Scripts\pip.exe"
Write-Host "Fetching latest release from GitHub..."
try {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
    $Asset = $Release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
    if ($Asset) {
        $TmpWhl = [System.IO.Path]::GetTempFileName() + ".whl"
        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $TmpWhl
        & $Pip install --upgrade --quiet $TmpWhl
        Remove-Item $TmpWhl -Force
    } else {
        & $Pip install --upgrade --quiet "git+https://github.com/$Repo.git"
    }
} catch {
    & $Pip install --upgrade --quiet "git+https://github.com/$Repo.git"
}

# Create wrapper script
$ShimPath = Join-Path $BinDir "harness-bridge.cmd"
"@echo off`n`"$VenvDir\Scripts\harness-bridge.exe`" %*" | Out-File -FilePath $ShimPath -Encoding ascii

Write-Host "=== Harness Bridge installed successfully to $ShimPath ===" -ForegroundColor Green
```

### Step 4.3: Create GitHub Actions Workflows
1. **`.github/workflows/ci.yml`**:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync

      - name: Run tests
        run: uv run pytest -v tests/
```

2. **`.github/workflows/release.yml`**:
```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  build-and-release:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Set up Python
        run: uv python install 3.13

      - name: Install dependencies & test
        run: |
          uv sync
          uv run pytest -v tests/

      - name: Build distributions
        run: uv build

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true
```

### Step 4.4: Create Test Suite in `tests/`
1. **`tests/conftest.py`**:
```python
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from harness_bridge.core.process import run_command_safe


@pytest.fixture
def temp_git_repo():
    """Create a temporary initialized git repository with an initial commit."""
    tmp_dir = tempfile.mkdtemp(prefix="hb_test_repo_")
    repo_path = Path(tmp_dir).resolve()

    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True)

    test_file = repo_path / "README.md"
    test_file.write_text("# Test Repository\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)

    yield repo_path

    shutil.rmtree(repo_path, ignore_errors=True)
```

2. **`tests/test_workspace.py`**:
```python
import pytest
from pathlib import Path
from harness_bridge.workspace.manager import WorkspaceManager


@pytest.mark.asyncio
async def test_workspace_inherit_mode(temp_git_repo):
    mgr = WorkspaceManager()
    ws = await mgr.prepare_workspace(mode="inherit", repo_root=temp_git_repo, session_id="test-session-1")
    assert ws == temp_git_repo


@pytest.mark.asyncio
async def test_workspace_worktree_isolation_and_diff(temp_git_repo):
    mgr = WorkspaceManager()
    session_id = "test-session-worktree"

    # 1. Prepare worktree
    ws = await mgr.prepare_workspace(mode="worktree", repo_root=temp_git_repo, session_id=session_id)
    assert ws.exists()
    assert (temp_git_repo / ".worktrees" / session_id) == ws

    # 2. Modify files and add a new untracked file in worktree
    (ws / "new_module.py").write_text("print('hello world')\n", encoding="utf-8")
    (ws / "README.md").write_text("# Test Repository Modified\n", encoding="utf-8")

    # 3. Extract diff
    diff = await mgr.extract_diff(ws)
    assert "new_module.py" in diff
    assert "Test Repository Modified" in diff

    # Verify main repo is pristine
    main_readme = (temp_git_repo / "README.md").read_text(encoding="utf-8")
    assert main_readme == "# Test Repository\n"
    assert not (temp_git_repo / "new_module.py").exists()

    # 4. Apply diff
    apply_res = await mgr.apply_diff(repo_root=temp_git_repo, session_id=session_id)
    assert apply_res.success is True
    assert (temp_git_repo / "new_module.py").exists()

    # 5. Cleanup
    await mgr.cleanup_workspace(session_id=session_id, worktree_path=ws, repo_root=temp_git_repo, delete_branch=True)
    assert not ws.exists()
```

3. **`tests/test_drivers.py`**:
```python
import pytest
from harness_bridge.drivers.registry import get_driver, list_all_harness_info
from harness_bridge.drivers.claude import ClaudeCodeDriver
from harness_bridge.drivers.antigravity import AntigravityDriver


def test_driver_registry():
    claude = get_driver("claude")
    assert isinstance(claude, ClaudeCodeDriver)
    assert claude.name == "claude"

    agy = get_driver("agy")
    assert isinstance(agy, AntigravityDriver)
    assert agy.name == "agy"

    antigravity_alias = get_driver("antigravity")
    assert antigravity_alias.name == "agy"


def test_list_harness_info():
    infos = list_all_harness_info()
    names = [i.name for i in infos]
    assert "claude" in names
    assert "agy" in names
```

4. **`tests/test_session.py`**:
```python
import pytest
from harness_bridge.core.exceptions import MaxHopsExceededError
from harness_bridge.core.types import TaskSpec
from harness_bridge.session.manager import SessionManager


@pytest.mark.asyncio
async def test_session_manager_hop_limit():
    mgr = SessionManager()
    spec = TaskSpec(
        harness="agy",
        prompt="echo test",
        hop_count=10,
        max_hops=10,
    )
    with pytest.raises(MaxHopsExceededError):
        await mgr.execute_task(spec)
```

5. **`tests/test_updater.py`**:
```python
import pytest
from harness_bridge.core.updater import parse_semver


def test_parse_semver():
    assert parse_semver("v0.1.0") == (0, 1, 0)
    assert parse_semver("0.2.1") == (0, 2, 1)
    assert parse_semver("v1.0.0-rc1") == (1, 0, 0)
    assert parse_semver("0.1.0") < parse_semver("0.2.0")
    assert parse_semver("1.0.0") > parse_semver("0.9.9")
```

6. **`tests/test_mcp_server.py`**:
```python
import pytest
from harness_bridge.server.mcp_server import mcp_app, bridge_list_harnesses


@pytest.mark.asyncio
async def test_mcp_list_harnesses_tool():
    tools = await bridge_list_harnesses()
    assert isinstance(tools, list)
    names = [t["name"] for t in tools]
    assert "claude" in names
    assert "agy" in names
```

---

## 5. Verification Commands

Run the full verification in the target repo:
```bash
cd /home/sukumar/sources/harness-bridge
uv sync
uv run pytest -v tests/
uv run harness-bridge list
uv run harness-bridge version
uv run harness-bridge test
```

---

## 6. GitHub Remote Publication

Once the tests pass:
```bash
cd /home/sukumar/sources/harness-bridge
git add .
git commit -m "feat: initial implementation of Harness Bridge"
gh repo create harness-bridge --public --source=. --remote=origin --push
```

---

## 7. Cleanup Note

After verifying everything works and pushing the repo, **delete this file (`HANDOFF.md`)** and commit the deletion:
```bash
rm HANDOFF.md
git add HANDOFF.md
git commit -m "chore: remove session handoff document"
git push
```
