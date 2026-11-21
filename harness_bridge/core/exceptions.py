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


class WorkerNotFoundError(HarnessBridgeError):
    """No active worker registered for the requested harness."""


class WorkerTimeoutError(HarnessBridgeError):
    """Worker disconnected or failed to renew lease before timeout."""


class TaskClaimConflictError(HarnessBridgeError):
    """Task has already been claimed by another worker."""


class BridgeLinkRequiredError(HarnessBridgeError):
    """Raised when multi-room operations are requested in local standalone mode."""


class BridgeLinkAuthenticationError(HarnessBridgeError):
    """Raised when Bridge-Link credentials are missing, invalid, or expired."""


class BridgeLinkNetworkError(HarnessBridgeError):
    """Raised when remote Bridge-Link API/SSE connection fails after retry exhaustion."""


class BridgeLinkAdmissionError(HarnessBridgeError):
    """Raised when an agent session is denied entry to a room (e.g. non-lead in summit room)."""
