## Description

Please include a summary of the changes and the related issue (if applicable).

Fixes #(issue)

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Driver addition (adds support for a new AI coding harness)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring / performance improvement

## Checklist

- [ ] My code follows the style guidelines of this project (`uv run ruff check` & `uv run ruff format`)
- [ ] I have performed a self-review of my own code
- [ ] **Stdio Cleanliness**: Verified that NO debug print statements write to `sys.stdout` (all logs route to `sys.stderr` to protect JSON-RPC framing)
- [ ] **Process Tree Lifecycle**: Subprocess commands are executed safely via `run_command_safe` with process-tree termination
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] All new and existing tests pass locally (`uv run pytest -v tests/`)
- [ ] Documentation updated if CLI options or MCP tools were changed
