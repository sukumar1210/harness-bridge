from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from harness_bridge.core.types import TaskResult, TaskSpec


class BaseDriver(ABC):
    """Abstract base class defining the execution interface for agent harness drivers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Normalized identifier for the harness (e.g. 'claude', 'agy')."""

    @property
    @abstractmethod
    def binary_name(self) -> str:
        """CLI executable binary name."""

    def resolve_binary(self) -> Path | None:
        """Resolve executable path using shutil.which."""
        path_str = shutil.which(self.binary_name)
        return Path(path_str).resolve() if path_str else None

    def is_installed(self) -> bool:
        """Check whether the binary is present on system PATH."""
        return self.resolve_binary() is not None

    @abstractmethod
    async def run_turn(
        self,
        task: TaskSpec,
        cwd: Path,
        env: dict[str, str],
    ) -> TaskResult:
        """Execute a single headless turn on the target harness."""
