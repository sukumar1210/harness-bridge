# Contributing to Harness Bridge

Thank you for your interest in contributing to Harness Bridge! We welcome contributions ranging from bug fixes and new driver integrations to documentation improvements and test coverage.

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- [`uv`](https://docs.astral.sh/uv/) (recommended for fast, deterministic virtual environments) or standard `python3-venv`

### Setting Up Local Environment

1. **Fork and Clone the Repository**:
   ```bash
   git clone https://github.com/<your-username>/harness-bridge.git
   cd harness-bridge
   ```

2. **Initialize Virtual Environment & Install Dependencies**:
   Using `uv` (recommended):
   ```bash
   uv sync
   ```
   Or using standard `venv` + `pip`:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Verify the Test Suite**:
   ```bash
   uv run pytest -v tests/
   # Or with activated venv:
   # pytest -v tests/
   ```

4. **Verify Local CLI Binary**:
   ```bash
   uv run harness-bridge --help
   uv run harness-bridge list
   ```

5. **Install Local Git Hooks (`pre-commit`)**:
   ```bash
   uv run pre-commit install
   ```
   This arms:
   - `pre-commit`: Executes sub-second Ruff linting and formatting fixes on staged files.
   - `commit-msg`: Enforces [Conventional Commits](https://www.conventionalcommits.org/) formatting via `scripts/validate_commit_msg.py`.

   > [!TIP]
   > **Optional Pre-Push Test Gating**: To automatically run the unit test suite locally before pushing commits, install the pre-push hook:
   > ```bash
   > uv run pre-commit install --hook-type pre-push
   > ```

   > [!NOTE]
   > **Emergency Escape Hatch**: In urgent emergencies or when rebasing intermediate work, hooks can be temporarily bypassed using the `--no-verify` flag:
   > ```bash
   > git commit -m "wip: emergency fix" --no-verify
   > git push origin my-branch --no-verify
   > ```

### Contributor Workflow ("Life of a Change")

1. **Branch**: Create a descriptive feature branch:
   ```bash
   git checkout -b feat/my-feature-name
   ```
2. **Develop**: Edit code in `harness_bridge/` and add corresponding tests in `tests/`.
3. **Validate**: Ensure all unit tests pass and code complies with formatting rules:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
4. **Submit PR**: Push your branch and open a pull request adhering to the guidelines below.

---

## Optional: Dual Environment Setup (Developing While Dogfooding)

> [!NOTE]
> This section is **optional**. It is intended for contributors who use an AI coding assistant (such as **Claude Code** or **Antigravity CLI**) *to develop* Harness Bridge itself.

### Why Separate Environments?

If your coding assistant uses Harness Bridge for its Model Context Protocol (MCP) tooling while you are actively modifying the codebase in your working tree, an in-progress refactor or syntax error could disrupt the assistant's runtime.

Maintaining a **two-tier separation** provides total isolation:
1. **Stable Deployed Instance**: Runs globally from an isolated directory (e.g. `<user-home>/.harness-bridge/venv/`), providing a dependable, frozen runtime for your AI assistant.
2. **Development Workspace**: Runs locally in your git clone (`/path/to/harness-bridge/.venv/`), where you can edit code, run experimental builds, and test breaking changes without impacting your assistant.

```
┌────────────────────────────────────────────────────────┐
│               Local Developer Workstation              │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
   STABLE DEPLOYED INSTANCE        DEVELOPMENT WORKSPACE
   (<user-home>/.harness-bridge/)  (/path/to/harness-bridge/)
               │                          │
  Frozen package (non-editable)   Editable install (uv / pip -e)
  Global command: harness-bridge  Binary: ./.venv/bin/harness-bridge
               │                          │
  Registered in harnesses as:     Registered in harnesses as:
  "harness-bridge"                "harness-bridge-dev"
  (Powers your daily assistant)   (Tests your WIP features)
```

| Environment Tier | Location | Packaging | Purpose |
| :--- | :--- | :--- | :--- |
| **Stable Deployment** (User Global) | `<user-home>/.harness-bridge/venv/` | Frozen release (`pip install git+...` or wheel) | Powers your daily AI assistant; isolated from repository edits. |
| **Development Workspace** (Repo Local) | `/path/to/harness-bridge/.venv/` | Editable install (`uv sync` or `pip install -e .`) | Local hacking, running `pytest`, and testing experimental features. |

---

### Step 1: Install the Stable Deployed Instance

Install the release build to your user home directory:

#### Linux / macOS:
```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/harness-bridge/main/scripts/install.sh | bash
```

#### Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/<owner>/harness-bridge/main/scripts/install.ps1 | iex
```

Verify that the global stable instance runs:
```bash
harness-bridge version
# Output: Harness Bridge v... (<user-home>/.harness-bridge/venv/bin/python)
```

---

### Step 2: Connect Both Instances to Your Coding Harnesses

Choose one of two configuration approaches:

#### Method A: Dual Server Registration (Recommended)
Register the local development virtual environment alongside the stable deployment under distinct server names. This allows your assistant to run on the stable server while you explicitly test in-progress features with the dev server.

##### 1. Antigravity CLI (`agy`)
Register the dev instance:
```bash
agy mcp add harness-bridge-dev /path/to/harness-bridge/.venv/bin/harness-bridge serve
```
Or configure in `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "harness-bridge",
      "args": ["serve"]
    },
    "harness-bridge-dev": {
      "command": "/path/to/harness-bridge/.venv/bin/harness-bridge",
      "args": ["serve"]
    }
  }
}
```

##### 2. Claude Code
Register the dev instance:
```bash
claude mcp add harness-bridge-dev -- /path/to/harness-bridge/.venv/bin/harness-bridge serve
```
Or configure in `~/.claude.json`:
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "harness-bridge",
      "args": ["serve"]
    },
    "harness-bridge-dev": {
      "command": "/path/to/harness-bridge/.venv/bin/harness-bridge",
      "args": ["serve"]
    }
  }
}
```

> [!TIP]
> **Safety Guarantee**: Your AI assistant communicates with `harness-bridge`. If you write broken code or introduce a syntax error in your local dev branch, only `harness-bridge-dev` will fail. Your assistant will **never** crash or lose conversational continuity.

---

#### Method B: Project-Scoped Override (`.mcp.json`)
If you prefer automatic switching based on working directory, place a `.mcp.json` file inside your cloned repository root:

```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "./.venv/bin/harness-bridge",
      "args": ["serve"]
    }
  }
}
```

* **Behavior**: When Claude Code or Antigravity operates inside `/path/to/harness-bridge/`, it automatically uses your local `.venv`. In any other directory or project, it automatically falls back to the global stable `harness-bridge`.

---

### Step 3: Upgrading the Stable Instance

Once your contributions are merged or ready for daily use, update your global stable deployment:

```bash
harness-bridge update
# Or update directly from git:
<user-home>/.harness-bridge/venv/bin/pip install --upgrade git+https://github.com/<owner>/harness-bridge.git
```

---

## Repository Structure

```
harness_bridge/
├── cli/          # Typer CLI application and user-facing commands
├── core/         # Process execution, custom exceptions, types, updater
├── drivers/      # Subprocess adapters for AI harnesses (claude, agy, etc.)
├── server/       # Stdio Model Context Protocol (MCP) server
├── session/      # Multi-turn session coordinator, hop tracing, loop protection
└── workspace/    # Ephemeral git worktree sandboxing & diff application
tests/            # Automated pytest test suite
scripts/          # Platform installation scripts (install.sh, install.ps1)
```

---

## Development Guidelines

### Adding a New Harness Driver

To add support for a new AI coding harness:
1. Inherit from `BaseDriver` in `harness_bridge/drivers/base.py`.
2. Implement `name`, `binary_name`, and `run_turn(task, cwd, env)`.
3. Register the new driver class in `harness_bridge/drivers/registry.py`.
4. Add corresponding unit tests in `tests/test_drivers.py`.

### Preserving Clean MCP Transport

When modifying server or process code:
- **Never** write debug logs to standard output (`sys.stdout`), as `stdout` is reserved strictly for JSON-RPC 2.0 MCP protocol framing.
- Always direct logging to `sys.stderr` or use `rich.console.Console(stderr=True)`.
- Use `run_command_safe` in `harness_bridge.core.process` to prevent pipe deadlocks on large subprocess outputs.

---

## Submitting Pull Requests

1. **Branch Naming**: Use descriptive branch names:
   - `feat/driver-copilot`
   - `fix/worktree-prune-error`
   - `docs/clarify-mcp-setup`

2. **Commit Messages & PR Titles**: Follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/):
   Format: `<type>(<optional scope>)[!]: <description>`
   - Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
   - Append `!` before the colon to denote breaking changes (e.g., `feat(server)!: redesign registration endpoint`)
   - Examples:
     - `feat(drivers): add driver for NewHarness`
     - `fix(workspace): handle edge case in diff generation`
     - `docs(contributing): update setup instructions in README`
     - `test(session): add coverage for session hop limit`
   - Both commit messages (locally) and PR titles (in CI) are strictly validated. Because squash merges use the PR title as the commit header on `main`, PR titles must conform to Conventional Commits.

3. **Draft PR Lifecycle & CI Resource Conservation**:
   - Open work-in-progress pull requests as **Draft**. GitHub Actions automatically skips the multi-OS test matrix for Draft PRs, conserving CI runner minutes.
   - When your implementation is complete and ready for review and CI verification, click **Ready for review**.
   - Marking a PR ready for review automatically triggers:
     - PR Title validation
     - Ruff linting and formatting across `harness_bridge`, `tests`, and `scripts`
     - The complete 9-permutation test matrix (Ubuntu, macOS, Windows across Python 3.11, 3.12, and 3.13)
     - The aggregate merge gate check: **`ci-passed`**
   - Protected branches (`main`, `rc`, and `rc/**`) require `ci-passed` to be successful before merging is allowed.

4. **Checklist Before Submitting**:
   - [ ] Local git hooks installed: `uv run pre-commit install`
   - [ ] All tests pass: `uv run pytest -v tests/`
   - [ ] Code formatted and linted: `uv run ruff check .` and `uv run ruff format .`
   - [ ] Commit message and PR title adhere to [Conventional Commits](https://www.conventionalcommits.org/)
   - [ ] New functionality includes unit/integration tests in `tests/`
   - [ ] Documentation updated if CLI options or configuration changed
   - [ ] Marked as "Ready for review" when ready for remote CI matrix gating

---

## Community & Questions

Feel free to open an issue or start a GitHub discussion to ask questions, propose features, or discuss architectural designs before starting a large pull request.
