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

- Join the [GitHub Discussions](https://github.com/sukumar1210/harness-bridge/discussions) to ask questions, discuss architecture, or brainstorm ideas.
- Vote on upcoming roadmap capabilities in our [Community Feature Voting & Roadmap Hub](https://github.com/sukumar1210/harness-bridge/discussions/16) or track the [Live Community Ideas Leaderboard](https://github.com/sukumar1210/harness-bridge/discussions/categories/ideas?discussions_q=is:open+category:Ideas+%22[Idea]%22+sort:top).
- For concrete bug reports or scoped engineering tasks, open an issue in the issue tracker.
