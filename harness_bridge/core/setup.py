from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harness_bridge.core.process import run_command_safe
from harness_bridge.drivers.registry import list_all_harness_info

SetupStatus = Literal["configured", "already_configured", "not_installed", "failed"]


@dataclass
class HarnessSetupResult:
    harness: str
    binary: str
    status: SetupStatus
    message: str


def check_claude_configured_fast() -> bool:
    """Fast check whether harness-bridge is registered in Claude Code configuration."""
    for claude_path in [
        Path.cwd() / ".mcp.json",
        Path.home() / ".claude.json",
    ]:
        if claude_path.exists():
            try:
                data = json.loads(claude_path.read_text(encoding="utf-8"))
                mcp_servers = data.get("mcpServers", {})
                if "harness-bridge" in mcp_servers:
                    return True
            except Exception:
                pass
    return False


def check_agy_configured_fast() -> bool:
    """Fast check whether harness-bridge is registered in Antigravity mcp_config.json."""
    for config_path in [
        Path.home() / ".gemini" / "config" / "mcp_config.json",
        Path.home() / ".gemini" / "antigravity-cli" / "mcp_config.json",
        Path.home() / ".gemini" / "antigravity" / "mcp_config.json",
    ]:
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                mcp_servers = data.get("mcpServers", {})
                if "harness-bridge" in mcp_servers:
                    return True
            except Exception:
                pass
    return False


async def setup_claude(
    executable: str = "harness-bridge",
    force: bool = False,
) -> HarnessSetupResult:
    """Configure Harness Bridge MCP server in Claude Code."""
    binary = shutil.which("claude")
    if not binary:
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="not_installed",
            message="Claude Code binary ('claude') not found on PATH.",
        )

    if not force and check_claude_configured_fast():
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="already_configured",
            message="Harness Bridge is already registered in Claude Code configuration.",
        )

    if force:
        await run_command_safe(["claude", "mcp", "remove", "harness-bridge"], timeout=10.0)

    # Register via claude mcp add harness-bridge -- <executable> serve
    cmd = ["claude", "mcp", "add", "harness-bridge", "--", executable, "serve"]
    code, stdout, stderr = await run_command_safe(cmd, timeout=15.0)
    output_combined = f"{stdout}\n{stderr}".lower()
    if "already exists" in output_combined or check_claude_configured_fast():
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="already_configured",
            message="Harness Bridge is already registered in Claude Code.",
        )
    if code == 0:
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="configured",
            message="Successfully registered Harness Bridge MCP server in Claude Code.",
        )
    return HarnessSetupResult(
        harness="claude",
        binary="claude",
        status="failed",
        message=f"Failed to configure Claude Code:\n{stderr or stdout}".strip(),
    )


async def setup_agy(
    executable: str = "harness-bridge",
    force: bool = False,
) -> HarnessSetupResult:
    """Configure Harness Bridge MCP server in Antigravity CLI."""
    binary = shutil.which("agy")
    if not binary:
        return HarnessSetupResult(
            harness="agy",
            binary="agy",
            status="not_installed",
            message="Antigravity CLI binary ('agy') not found on PATH.",
        )

    if not force and check_agy_configured_fast():
        return HarnessSetupResult(
            harness="agy",
            binary="agy",
            status="already_configured",
            message="Harness Bridge is already registered in Antigravity configuration.",
        )

    if force:
        await run_command_safe(["agy", "mcp", "remove", "harness-bridge"], timeout=10.0)

    # Register via agy mcp add harness-bridge <executable> serve
    cmd = ["agy", "mcp", "add", "harness-bridge", executable, "serve"]
    code, stdout, stderr = await run_command_safe(cmd, timeout=15.0)
    if code == 0 or check_agy_configured_fast():
        return HarnessSetupResult(
            harness="agy",
            binary="agy",
            status="configured",
            message="Successfully registered Harness Bridge MCP server in Antigravity CLI.",
        )
    return HarnessSetupResult(
        harness="agy",
        binary="agy",
        status="failed",
        message=f"Failed to configure Antigravity CLI:\n{stderr or stdout}".strip(),
    )


async def setup_all_harnesses(
    executable: str | None = None,
    force: bool = False,
) -> list[HarnessSetupResult]:
    """Auto-detect all installed harnesses and register Harness Bridge MCP server in each."""
    target_exec = executable or shutil.which("harness-bridge") or "harness-bridge"

    results: list[HarnessSetupResult] = []

    # Get all registered harnesses
    harnesses = {h.name: h for h in list_all_harness_info()}

    if "claude" in harnesses:
        claude_res = await setup_claude(executable=target_exec, force=force)
        results.append(claude_res)

    if "agy" in harnesses:
        agy_res = await setup_agy(executable=target_exec, force=force)
        results.append(agy_res)

    return results
