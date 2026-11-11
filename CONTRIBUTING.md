# Contributing to Harness Bridge

Thank you for your interest in contributing to Harness Bridge! We welcome contributions ranging from bug fixes and new driver integrations to documentation improvements and test coverage.

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- [`uv`](https://docs.astral.sh/uv/) (recommended for fast, deterministic virtual environments)

### Setting Up Local Environment

1. Fork the repository on GitHub and clone your fork:
   ```bash
   git clone https://github.com/<your-username>/harness-bridge.git
   cd harness-bridge
   ```

2. Synchronize virtual environment and install dependencies:
   ```bash
   uv sync
   ```

3. Verify test suite passes:
   ```bash
   uv run pytest -v tests/
   ```

4. Verify local CLI binary runs:
   ```bash
   uv run harness-bridge --help
   uv run harness-bridge list
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

2. **Commit Messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add driver for NewHarness`
   - `fix: handle edge case in diff generation`
   - `docs: update setup instructions in README`
   - `test: add coverage for session hop limit`

3. **Checklist Before Submitting**:
   - [ ] All tests pass: `uv run pytest -v tests/`
   - [ ] New functionality includes unit/integration tests in `tests/`
   - [ ] Documentation updated if CLI options or configuration changed

---

## Community & Questions

Feel free to open an issue or start a GitHub discussion to ask questions, propose features, or discuss architectural designs before starting a large pull request.
