from __future__ import annotations


class HarnessBridgeError(Exception):
    """Base exception for Harness Bridge."""


class HarnessNotFoundError(HarnessBridgeError):
    """Target harness CLI binary was not found on host system."""


class SessionTimeoutError(HarnessBridgeError):
    """Task or turn execution exceeded allotted timeout."""


class MaxHopsExceededError(HarnessBridgeError):
    """Distributed delegation recursion ceiling reached."""


class WorkspaceError(HarnessBridgeError):
    """Git worktree or workspace manipulation failed."""


class UpdateError(HarnessBridgeError):
    """Self-update check, download, or upgrade execution failed."""
