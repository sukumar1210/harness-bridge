from __future__ import annotations

from harness_bridge.core.exceptions import HarnessNotFoundError
from harness_bridge.core.types import HarnessInfo
from harness_bridge.drivers.antigravity import AntigravityDriver
from harness_bridge.drivers.base import BaseDriver
from harness_bridge.drivers.claude import ClaudeCodeDriver

_DRIVERS: dict[str, BaseDriver] = {
    "claude": ClaudeCodeDriver(),
    "agy": AntigravityDriver(),
    "antigravity": AntigravityDriver(),  # Alias
}


def get_driver(name: str) -> BaseDriver:
    """Retrieve driver by normalized name or alias."""
    norm = name.lower().strip()
    driver = _DRIVERS.get(norm)
    if not driver:
        available = ", ".join(sorted(set(_DRIVERS.keys())))
        raise HarnessNotFoundError(f"Unknown harness '{name}'. Available: {available}")
    return driver


def list_unique_drivers() -> list[BaseDriver]:
    """Return unique registered driver instances."""
    seen = set()
    unique = []
    for d in _DRIVERS.values():
        if d.name not in seen:
            seen.add(d.name)
            unique.append(d)
    return unique


def get_harness_info(driver: BaseDriver) -> HarnessInfo:
    """Inspect driver and return installation status."""
    bin_path = driver.resolve_binary()
    return HarnessInfo(
        name=driver.name,
        binary=driver.binary_name,
        installed=bin_path is not None,
        path=str(bin_path) if bin_path else None,
    )


def list_all_harness_info() -> list[HarnessInfo]:
    """Inspect all registered harnesses and return their status."""
    return [get_harness_info(d) for d in list_unique_drivers()]
