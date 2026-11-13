# Platform Scripts (`scripts`)

## Overview
The `scripts` directory provides platform-native, zero-dependency bootstrapping scripts for installing and configuring **Harness Bridge** across Unix (Linux/macOS) and Windows environments, as well as developer tooling scripts for local git hook enforcement.

## Interface

### 1. Developer Tooling & Git Hooks
- `python scripts/validate_commit_msg.py <commit_msg_file>`:
  - **Platform**: Cross-platform (Linux, macOS, Windows).
  - **Prerequisites**: Python 3.11+. Standard library only (zero external package dependencies).
  - **Usage**: Automatically invoked by `.pre-commit-config.yaml` during the Git `commit-msg` hook stage, receiving the path to `.git/COMMIT_EDITMSG`.
  - **Contract & Behavior**:
    - Strips git comment lines (starting with `#`) and empty lines.
    - Matches header against Conventional Commits v1.0.0: `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_\-\./]+\))?(!)?: [^\n\r]+`.
    - Automatically bypasses merge commits (`Merge (remote-tracking )?branch`, `Merge branches?`, `Merge pull request`, `Merge tag`) and revert commits (`Revert "..."`).
    - On validation failure: prints actionable diagnostic guidance to `sys.stderr`, displays the exact rejected commit header, allowed types, format examples, and the specification link (`https://www.conventionalcommits.org/`), exiting with code `1`.
    - On validation success: exits with code `0`.

### 2. Platform Installation & Bootstrapping
- `bash scripts/install.sh`:
  - **Platform**: Linux, macOS, and POSIX-compliant environments.
  - **Options / Flags**: Executes non-interactively without requiring CLI flags. Can be piped directly via `curl -fsSL <url> | bash`.
  - **Prerequisites**: `python3` (Python 3.11+ with `venv` module), `curl`, `grep`, `mktemp`.
  - **Output**: Installs CLI binary symlink at `~/.local/bin/harness-bridge`.
- `powershell -ExecutionPolicy Bypass -File scripts/install.ps1`:
  - **Platform**: Windows (PowerShell 5.1+ or PowerShell Core 7+).
  - **Options / Flags**: Executes non-interactively without requiring CLI flags. Can be invoked via `irm <url> | iex`.
  - **Prerequisites**: `python` (Python 3.11+ with `venv` module on system `PATH`).
  - **Output**: Generates command wrapper shim at `~/.local\bin\harness-bridge.cmd`.

## Invariants
- **Zero External Dependencies**: All scripts in `scripts/` require only standard system utilities and standard library Python without requiring pre-installed pip packages.
- **Shell Compatibility**: `install.sh` uses strict bash execution flags (`set -euo pipefail`) to halt immediately on unhandled command failures or unset variables. `install.ps1` sets `$ErrorActionPreference = "Stop"` for strict error termination.
- **User-Space Isolation**: All installation actions target the invoking user's home directory (`~/.harness-bridge` and `~/.local/bin`), never requiring superuser or administrative privileges.
- **Non-Destructive Provisioning**: Reuses existing virtual environment directories (`~/.harness-bridge/venv`) if already present rather than rebuilding from scratch.
- **Release Fallback Guarantee**: Queries GitHub Releases API for latest pre-compiled `.whl` asset; automatically falls back to `git+https://github.com/sukumar1210/harness-bridge.git` if release assets are unavailable or API calls fail.
- **Artifact Cleanup**: Temporary downloaded wheel files are cleaned up immediately following pip installation (`rm -f` or `Remove-Item -Force`).
- **Idempotency**: Scripts can be safely executed repeatedly to update or repair the installation.

## Side Effects
- **Directory Creation**: Creates `~/.harness-bridge` and `~/.local/bin` (or Windows `%USERPROFILE%\.harness-bridge` and `%USERPROFILE%\.local\bin`) if they do not exist.
- **Virtualenv Provisioning**: Initializes an isolated Python virtual environment at `~/.harness-bridge/venv`.
- **Pip Installation & Network Egress**: Issues outbound HTTPS requests to `api.github.com` and GitHub release assets/repositories; installs or upgrades the `harness-bridge` package and dependencies via `pip`.
- **Executable Symlinking / Shim Generation**:
  - Unix: Overwrites symlink at `~/.local/bin/harness-bridge` pointing to `~/.harness-bridge/venv/bin/harness-bridge`.
  - Windows: Writes command wrapper batch script at `~/.local\bin\harness-bridge.cmd` invoking `~/.harness-bridge\venv\Scripts\harness-bridge.exe`.
- **Console Output**: Emits status messages and PATH configuration reminders to `stdout` / `stderr`.

## Verification
- Test Commit Validator: `python scripts/validate_commit_msg.py <(echo "feat: test message")`
- Test Install Script: `bash scripts/install.sh --help 2>&1 || true`
