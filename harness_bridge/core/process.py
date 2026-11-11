from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path


async def terminate_process_tree(proc: asyncio.subprocess.Process, timeout: float = 3.0) -> None:
    """Terminate a process and all its child processes in a cross-platform manner."""
    if proc.returncode is not None:
        return

    if sys.platform == "win32":
        try:
            proc.terminate()
        except ProcessLookupError:
            return
    else:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except ProcessLookupError:
                return

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except TimeoutError:
        if sys.platform == "win32":
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        else:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass


async def run_command_safe(
    args: list[str],
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> tuple[int, str, str]:
    """Execute a subprocess safely using proc.communicate() to avoid pipe buffer deadlocks."""
    kwargs: dict = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if cwd is not None:
        kwargs["cwd"] = str(cwd)
    if env is not None:
        kwargs["env"] = env

    if sys.platform != "win32":
        kwargs["process_group"] = 0

    proc = await asyncio.create_subprocess_exec(*args, **kwargs)

    try:
        async with asyncio.timeout(timeout):
            stdout_bytes, stderr_bytes = await proc.communicate()
    except TimeoutError:
        await terminate_process_tree(proc, timeout=2.0)
        raise TimeoutError(f"Command timed out after {timeout} seconds: {' '.join(args)}")

    stdout_str = stdout_bytes.decode("utf-8", errors="replace")
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = proc.returncode if proc.returncode is not None else -1

    return exit_code, stdout_str, stderr_str
