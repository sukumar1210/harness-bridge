from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def terminate_pid_group(pid: int, timeout: float = 2.0) -> None:
    """Terminate an entire process group by PID across platforms."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return

        time.sleep(0.1)
        try:
            # Probe if still alive
            os.kill(pid, 0)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


async def terminate_process_tree(proc: asyncio.subprocess.Process, timeout: float = 3.0) -> None:
    """Terminate a process and all its child processes in a cross-platform manner."""
    if proc.returncode is not None:
        return

    pid = proc.pid
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            proc.terminate()
        except Exception:
            try:
                proc.terminate()
            except ProcessLookupError:
                return
    else:
        try:
            pgid = os.getpgid(pid)
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
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass


async def _read_stream(
    stream: asyncio.StreamReader | None,
    chunks: list[bytes],
    log_file: Any | None = None,
) -> None:
    """Read stream lines asynchronously and incrementally write to log file."""
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            break
        chunks.append(line)
        if log_file:
            try:
                log_file.write(line)
                log_file.flush()
            except Exception:
                pass


async def run_command_safe(
    args: list[str],
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 300.0,
    log_path: Path | None = None,
    pid_callback: Callable[[int], None] | None = None,
) -> tuple[int, str, str]:
    """Execute a subprocess safely with streaming logs and process-group cancellation."""
    kwargs: dict = {
        "stdin": asyncio.subprocess.DEVNULL,
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

    if pid_callback and proc.pid:
        try:
            pid_callback(proc.pid)
        except Exception:
            pass

    log_file = None
    if log_path:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = open(log_path, "ab")
        except Exception:
            log_file = None

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(
                _read_stream(proc.stdout, stdout_chunks, log_file),
                _read_stream(proc.stderr, stderr_chunks, log_file),
            )
            await proc.wait()
    except (TimeoutError, asyncio.CancelledError) as exc:
        await terminate_process_tree(proc, timeout=2.0)
        if isinstance(exc, TimeoutError):
            raise TimeoutError(f"Command timed out after {timeout} seconds: {' '.join(args)}")
        raise
    finally:
        if log_file:
            try:
                log_file.close()
            except Exception:
                pass

    stdout_str = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr_str = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    exit_code = proc.returncode if proc.returncode is not None else -1

    return exit_code, stdout_str, stderr_str
