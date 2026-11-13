"""Tests for scripts/validate_commit_msg.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

VALIDATOR_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_commit_msg.py"


def run_validator(commit_text: str | None, *extra_args: str) -> subprocess.CompletedProcess[str]:
    """Helper to execute validate_commit_msg.py with a synthetic commit message file."""
    import os

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    if commit_text is None:
        cmd = [sys.executable, str(VALIDATOR_SCRIPT), *extra_args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    # Create temporary commit message file
    import tempfile

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
        f.write(commit_text)
        temp_path = f.name

    try:
        cmd = [sys.executable, str(VALIDATOR_SCRIPT), temp_path, *extra_args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.parametrize(
    "msg",
    [
        "feat: add driver",
        "fix(session): resolve pipe deadlock",
        "docs(contributing): update guide",
        "feat(drivers)!: breaking api change",
        "chore: update dependencies",
        "refactor(core/process): simplify subprocess execution",
        "style: format with ruff",
        "perf(server): optimize json-rpc framing",
        "test: add test suite for validator",
        "build(deps): bump pre-commit version",
        "ci: configure github actions workflow",
        "revert: restore previous commit",
        # Multi-line commit with comments and body
        "# Please enter the commit message for your changes.\n\nfeat(cli): add setup subcommand\n\nDetailed body explanation.",
    ],
)
def test_valid_conventional_commits(msg: str) -> None:
    res = run_validator(msg)
    assert res.returncode == 0, f"Expected valid commit, got error: {res.stderr}"
    assert res.stderr == ""


@pytest.mark.parametrize(
    "msg",
    [
        "added driver changes",
        "FEAT: uppercase type is not allowed",
        "fix:",
        "fix: ",
        "wip",
        "unknown(scope): unsupported type",
        "feat(bad scope): spaces in scope are invalid",
        "feat(): empty scope parentheses",
    ],
)
def test_invalid_conventional_commits_rejected(msg: str) -> None:
    res = run_validator(msg)
    assert res.returncode == 1
    assert "[COMMIT REJECTED] Non-Compliant Commit Message Format" in res.stderr
    assert "https://www.conventionalcommits.org/" in res.stderr
    assert (
        "Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
        in res.stderr
    )


@pytest.mark.parametrize(
    "bypass_msg",
    [
        "Merge remote-tracking branch 'origin/main' into feature",
        "Merge branch 'main' of https://github.com/sukumar1210/harness-bridge",
        "Merge branches 'feat/a' and 'feat/b'",
        "Merge pull request #42 from owner/branch",
        "Merge tag 'v0.1.0' into main",
        'Revert "feat(drivers): add driver"',
        'Revert "fix: broken pipe"\n\nThis reverts commit 123456.',
    ],
)
def test_git_pull_and_merge_bypass_patterns(bypass_msg: str) -> None:
    res = run_validator(bypass_msg)
    assert res.returncode == 0, f"Expected bypass to pass, got error: {res.stderr}"


def test_empty_commit_message_rejected() -> None:
    res = run_validator("")
    assert res.returncode == 1
    assert "Error: Empty commit message." in res.stderr


def test_comments_only_commit_message_rejected() -> None:
    res = run_validator("# This is a comment\n# Another comment line\n")
    assert res.returncode == 1
    assert "Error: Empty commit message." in res.stderr


def test_missing_argument_exits_with_error() -> None:
    res = run_validator(None)
    assert res.returncode == 1
    assert "Error: commit message file path not provided." in res.stderr
