from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness_bridge.core.exceptions import HarnessNotFoundError
from harness_bridge.core.process import run_command_safe
from harness_bridge.core.types import SessionStatus, TaskResult, TaskSpec, TokenUsage
from harness_bridge.drivers.base import BaseDriver


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    """Robustly extract structured JSON payload from harness stdout."""
    clean = text.strip()
    if not clean:
        return None
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    for line in reversed(clean.splitlines()):
        trimmed = line.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return None


class AntigravityDriver(BaseDriver):
    """Driver for Google's Antigravity CLI (agy) harness."""

    @property
    def name(self) -> str:
        return "agy"

    @property
    def binary_name(self) -> str:
        return "agy"

    async def run_turn(
        self,
        task: TaskSpec,
        cwd: Path,
        env: dict[str, str],
        log_path: Path | None = None,
        pid_callback: Callable[[int], None] | None = None,
    ) -> TaskResult:
        binary = self.resolve_binary()
        if not binary:
            raise HarnessNotFoundError(
                f"Antigravity CLI binary '{self.binary_name}' not found on PATH."
            )

        cmd = [
            str(binary),
            "-p",
            task.prompt,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
        ]

        if task.is_resume:
            # Use native conversation ID if resolved; fallback to task.session_id
            resume_id = task.harness_session_id or task.session_id
            if resume_id:
                cmd.extend(["--conversation", resume_id])

        # Ensure no interactive Antigravity session variables leak into child agy
        clean_env = dict(env)
        for var in (
            "ANTIGRAVITY_CONVERSATION_ID",
            "ANTIGRAVITY_LS_ADDRESS",
            "ANTIGRAVITY_CSRF_TOKEN",
            "ANTIGRAVITY_TRAJECTORY_ID",
            "ANTIGRAVITY_PROJECT_ID",
            "ANTIGRAVITY_AGENT",
            "ANTIGRAVITY_SOURCE_METADATA",
            "ANTIGRAVITY_AGENTAPI_EXE",
        ):
            clean_env.pop(var, None)

        # Ephemeral session sandbox: isolate SQLite DBs and transcripts from host ~/.gemini
        if task.session_id:
            import tempfile

            sandbox_dir = (
                Path(tempfile.gettempdir())
                / "harness-bridge"
                / "sandboxes"
                / task.session_id
                / "antigravity-cli"
            )
            try:
                sandbox_dir.mkdir(parents=True, exist_ok=True)
                # Selective credential bridge: link/copy installation_id if host has one
                host_app_dir = Path.home() / ".gemini" / "antigravity-cli"
                host_install_id = host_app_dir / "installation_id"
                sandbox_install_id = sandbox_dir / "installation_id"
                if host_install_id.exists() and not sandbox_install_id.exists():
                    try:
                        sandbox_install_id.write_text(
                            host_install_id.read_text(encoding="utf-8"), encoding="utf-8"
                        )
                    except Exception:
                        pass
                clean_env["ANTIGRAVITY_APP_DATA_DIR"] = str(sandbox_dir)
            except Exception:
                pass

        start_time = time.perf_counter()
        exit_code, stdout, stderr = await run_command_safe(
            cmd,
            cwd=cwd,
            env=clean_env,
            timeout=float(task.timeout_seconds),
            log_path=log_path,
            pid_callback=pid_callback,
        )
        duration = time.perf_counter() - start_time

        output_text = stdout.strip()
        status: SessionStatus = "completed" if exit_code == 0 else "failed"

        harness_session_id = task.harness_session_id
        token_usage: TokenUsage | None = None
        num_turns: int | None = None
        metadata: dict[str, Any] = {}

        data = _extract_json_payload(output_text)
        if data:
            # Extract Antigravity's native conversation ID
            native_id = data.get("conversation_id") or data.get("session_id")
            if native_id:
                harness_session_id = str(native_id)
                metadata["agy_conversation_id"] = str(native_id)

            # Extract result text
            if "result" in data:
                output_text = str(data["result"])
            elif "response" in data:
                output_text = str(data["response"])

            # Extract usage metrics
            usage_dict = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            inp = usage_dict.get("input_tokens") or data.get("input_tokens") or 0
            out = usage_dict.get("output_tokens") or data.get("output_tokens") or 0
            tot = usage_dict.get("total_tokens") or (inp + out)
            cost = data.get("cost_usd") or data.get("cost")

            if inp or out or tot or cost is not None:
                token_usage = TokenUsage(
                    input_tokens=int(inp),
                    output_tokens=int(out),
                    total_tokens=int(tot),
                    cost_usd=float(cost) if cost is not None else None,
                )

            turns_val = data.get("num_turns") or data.get("turns")
            if turns_val is not None:
                try:
                    num_turns = int(turns_val)
                except (ValueError, TypeError):
                    pass

        if exit_code != 0 and not output_text:
            output_text = stderr.strip()

        return TaskResult(
            session_id=task.session_id or "",
            harness=self.name,
            status=status,
            output=output_text,
            diff=None,
            exit_code=exit_code,
            duration_seconds=round(duration, 3),
            harness_session_id=harness_session_id,
            usage=token_usage,
            num_turns=num_turns,
            driver_metadata=metadata,
        )
