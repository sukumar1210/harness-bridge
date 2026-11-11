from __future__ import annotations

import json
import time
from pathlib import Path

from harness_bridge.core.exceptions import HarnessNotFoundError
from harness_bridge.core.process import run_command_safe
from harness_bridge.core.types import SessionStatus, TaskResult, TaskSpec
from harness_bridge.drivers.base import BaseDriver


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

        if task.session_id:
            cmd.extend(["--conversation", task.session_id])

        start_time = time.perf_counter()
        exit_code, stdout, stderr = await run_command_safe(
            cmd,
            cwd=cwd,
            env=env,
            timeout=float(task.timeout_seconds),
        )
        duration = time.perf_counter() - start_time

        output_text = stdout.strip()
        status: SessionStatus = "completed" if exit_code == 0 else "failed"

        # Attempt to parse structured JSON output if emitted
        if output_text:
            try:
                data = json.loads(output_text)
                if isinstance(data, dict):
                    if "result" in data:
                        output_text = str(data["result"])
                    elif "response" in data:
                        output_text = str(data["response"])
            except json.JSONDecodeError:
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
        )
