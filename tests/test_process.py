from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from harness_bridge.core.process import (
    run_command_safe,
    terminate_pid_group,
    terminate_process_tree,
)


@pytest.mark.asyncio
async def test_run_command_safe_timeout():
    """Verify run_command_safe raises TimeoutError and terminates process group on timeout."""
    with pytest.raises(TimeoutError, match="Command timed out"):
        await run_command_safe(
            ["python3", "-c", "import time; time.sleep(10)"],
            timeout=0.2,
        )


@pytest.mark.asyncio
async def test_run_command_safe_pid_callback():
    """Verify pid_callback is called with child pid."""
    captured_pids = []
    exit_code, stdout, stderr = await run_command_safe(
        ["python3", "-c", "print('hello pid')"],
        pid_callback=lambda p: captured_pids.append(p),
    )
    assert exit_code == 0
    assert len(captured_pids) == 1
    assert captured_pids[0] > 0


@pytest.mark.asyncio
async def test_terminate_pid_group_nonexistent():
    """Verify terminate_pid_group handles nonexistent PID without throwing."""
    # PID 99999999 does not exist
    terminate_pid_group(99999999)


@pytest.mark.asyncio
async def test_terminate_process_tree_completed_process():
    """Verify terminate_process_tree safely returns if process has already completed."""
    proc = await asyncio.create_subprocess_exec(
        "python3",
        "-c",
        "print('done')",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    assert proc.returncode is not None
    # Should be a no-op
    await terminate_process_tree(proc)


@pytest.mark.asyncio
async def test_run_command_safe_log_path(tmp_path: Path):
    """Verify output is written incrementally to log_path."""
    log_file = tmp_path / "test.log"
    exit_code, stdout, stderr = await run_command_safe(
        ["python3", "-c", "import sys; print('log line 1'); sys.stderr.write('err line 1\\n')"],
        log_path=log_file,
    )
    assert exit_code == 0
    assert "log line 1" in stdout
    assert "err line 1" in stderr
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "log line 1" in content
    assert "err line 1" in content


@pytest.mark.asyncio
async def test_run_command_safe_env_and_cwd(tmp_path: Path):
    """Verify custom environment and working directory are passed."""
    exit_code, stdout, _ = await run_command_safe(
        ["python3", "-c", "import os; print(os.environ.get('MY_TEST_VAR'), os.getcwd())"],
        cwd=tmp_path,
        env={"MY_TEST_VAR": "custom_val"},
    )
    assert exit_code == 0
    assert "custom_val" in stdout
    assert str(tmp_path.resolve()) in stdout


@pytest.mark.asyncio
async def test_terminate_process_tree_live_process():
    """Verify terminate_process_tree kills an active process."""
    proc = await asyncio.create_subprocess_exec(
        "python3",
        "-c",
        "import time; time.sleep(30)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.returncode is None
    await terminate_process_tree(proc, timeout=1.0)
    assert proc.returncode is not None


def test_terminate_pid_group_live_process():
    """Verify terminate_pid_group kills a live process group."""
    import subprocess

    proc = subprocess.Popen(
        ["python3", "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    try:
        assert proc.poll() is None
        terminate_pid_group(proc.pid, timeout=1.0)
        proc.wait(timeout=2.0)
        assert proc.returncode is not None
    finally:
        if proc.poll() is None:
            proc.kill()
