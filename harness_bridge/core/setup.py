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


def build_docker_run_args(docker_image: str = "harness-bridge:latest") -> list[str]:
    """Generate the docker run arguments for MCP server registration."""
    home_dir = str(Path.home())
    cwd_dir = str(Path.cwd().resolve())

    mounts: list[str] = [
        "-v",
        f"{home_dir}:{home_dir}",
    ]
    if Path("/srv").exists():
        mounts.extend(["-v", "/srv:/srv"])
    if cwd_dir != home_dir and not cwd_dir.startswith(home_dir) and not cwd_dir.startswith("/srv"):
        mounts.extend(["-v", f"{cwd_dir}:{cwd_dir}"])
    mounts.extend(["-v", f"{cwd_dir}:/workspace"])
    mounts.extend(["-v", "harness-bridge-data:/home/bridge/.harness-bridge"])

    return [
        "docker",
        "run",
        "-i",
        "--rm",
        *mounts,
        docker_image,
        "serve",
    ]


def check_claude_configured_fast(for_docker: bool = False) -> bool:
    """Fast check whether harness-bridge is registered in Claude Code configuration."""
    for claude_path in [
        Path.cwd() / ".mcp.json",
        Path.home() / ".claude.json",
    ]:
        if claude_path.exists():
            try:
                data = json.loads(claude_path.read_text(encoding="utf-8"))
                mcp_servers = data.get("mcpServers", {})
                cfg = mcp_servers.get("harness-bridge")
                if cfg:
                    if for_docker:
                        cmd = cfg.get("command", "") if isinstance(cfg, dict) else ""
                        return cmd == "docker"
                    return True
            except Exception:
                pass
    return False


def check_agy_configured_fast(for_docker: bool = False) -> bool:
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
                cfg = mcp_servers.get("harness-bridge")
                if cfg:
                    if for_docker:
                        cmd = cfg.get("command", "") if isinstance(cfg, dict) else ""
                        return cmd == "docker"
                    return True
            except Exception:
                pass
    return False


async def setup_claude(
    executable: str = "harness-bridge",
    force: bool = False,
    use_docker: bool = False,
    docker_image: str = "harness-bridge:latest",
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

    if not force and check_claude_configured_fast(for_docker=use_docker):
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="already_configured",
            message=f"Harness Bridge is already registered in Claude Code configuration ({'docker' if use_docker else 'local'}).",
        )

    # Remove existing registration before adding new one
    await run_command_safe(["claude", "mcp", "remove", "harness-bridge"], timeout=10.0)

    # Register via claude mcp add -s user harness-bridge -- <command>
    if use_docker:
        docker_cmd = build_docker_run_args(docker_image=docker_image)
        cmd = ["claude", "mcp", "add", "-s", "user", "harness-bridge", "--", *docker_cmd]
    else:
        cmd = ["claude", "mcp", "add", "-s", "user", "harness-bridge", "--", executable, "serve"]
    code, stdout, stderr = await run_command_safe(cmd, timeout=15.0)
    if code == 0:
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="configured",
            message=f"Successfully registered Harness Bridge MCP server in Claude Code ({'docker' if use_docker else 'local'}).",
        )

    # Fallback: direct write to ~/.claude.json if CLI fails or behaves non-interactively
    claude_cfg_file = Path.home() / ".claude.json"
    try:
        claude_cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_data = (
            json.loads(claude_cfg_file.read_text(encoding="utf-8"))
            if claude_cfg_file.exists()
            else {}
        )
        if "mcpServers" not in cfg_data:
            cfg_data["mcpServers"] = {}
        if use_docker:
            docker_cmd = build_docker_run_args(docker_image=docker_image)
            cfg_data["mcpServers"]["harness-bridge"] = {
                "type": "stdio",
                "command": docker_cmd[0],
                "args": docker_cmd[1:],
                "env": {},
            }
        else:
            cfg_data["mcpServers"]["harness-bridge"] = {
                "type": "stdio",
                "command": executable,
                "args": ["serve"],
                "env": {},
            }
        claude_cfg_file.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
        return HarnessSetupResult(
            harness="claude",
            binary="claude",
            status="configured",
            message=f"Successfully registered Harness Bridge MCP server in Claude Code configuration ({'docker' if use_docker else 'local'}).",
        )
    except Exception:
        pass

    return HarnessSetupResult(
        harness="claude",
        binary="claude",
        status="failed",
        message=f"Failed to configure Claude Code:\n{stderr or stdout}".strip(),
    )


async def setup_agy(
    executable: str = "harness-bridge",
    force: bool = False,
    use_docker: bool = False,
    docker_image: str = "harness-bridge:latest",
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

    if not force and check_agy_configured_fast(for_docker=use_docker):
        return HarnessSetupResult(
            harness="agy",
            binary="agy",
            status="already_configured",
            message=f"Harness Bridge is already registered in Antigravity configuration ({'docker' if use_docker else 'local'}).",
        )

    # Remove existing registration before adding new one
    await run_command_safe(["agy", "mcp", "remove", "harness-bridge"], timeout=10.0)

    # Register via agy mcp add harness-bridge -- <command>
    if use_docker:
        docker_cmd = build_docker_run_args(docker_image=docker_image)
        cmd = ["agy", "mcp", "add", "harness-bridge", "--", *docker_cmd]
    else:
        cmd = ["agy", "mcp", "add", "harness-bridge", executable, "serve"]
    code, stdout, stderr = await run_command_safe(cmd, timeout=15.0)
    if code == 0:
        return HarnessSetupResult(
            harness="agy",
            binary="agy",
            status="configured",
            message=f"Successfully registered Harness Bridge MCP server in Antigravity CLI ({'docker' if use_docker else 'local'}).",
        )

    # Fallback: direct write to ~/.gemini/config/mcp_config.json if CLI fails
    agy_cfg_file = Path.home() / ".gemini" / "config" / "mcp_config.json"
    try:
        agy_cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_data = (
            json.loads(agy_cfg_file.read_text(encoding="utf-8")) if agy_cfg_file.exists() else {}
        )
        if "mcpServers" not in cfg_data:
            cfg_data["mcpServers"] = {}
        if use_docker:
            docker_cmd = build_docker_run_args(docker_image=docker_image)
            cfg_data["mcpServers"]["harness-bridge"] = {
                "command": docker_cmd[0],
                "args": docker_cmd[1:],
            }
        else:
            cfg_data["mcpServers"]["harness-bridge"] = {
                "command": executable,
                "args": ["serve"],
            }
        agy_cfg_file.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
        return HarnessSetupResult(
            harness="agy",
            binary="agy",
            status="configured",
            message=f"Successfully registered Harness Bridge MCP server in Antigravity CLI configuration ({'docker' if use_docker else 'local'}).",
        )
    except Exception:
        pass

    return HarnessSetupResult(
        harness="agy",
        binary="agy",
        status="failed",
        message=f"Failed to configure Antigravity CLI:\n{stderr or stdout}".strip(),
    )


async def setup_all_harnesses(
    executable: str | None = None,
    force: bool = False,
    use_docker: bool = False,
    docker_image: str = "harness-bridge:latest",
) -> list[HarnessSetupResult]:
    """Auto-detect all installed harnesses and register Harness Bridge MCP server in each."""
    target_exec = executable or shutil.which("harness-bridge") or "harness-bridge"

    results: list[HarnessSetupResult] = []

    # Get all registered harnesses
    harnesses = {h.name: h for h in list_all_harness_info()}

    if "claude" in harnesses:
        claude_res = await setup_claude(
            executable=target_exec,
            force=force,
            use_docker=use_docker,
            docker_image=docker_image,
        )
        results.append(claude_res)

    if "agy" in harnesses:
        agy_res = await setup_agy(
            executable=target_exec,
            force=force,
            use_docker=use_docker,
            docker_image=docker_image,
        )
        results.append(agy_res)

    return results
