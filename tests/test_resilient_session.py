from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from harness_bridge.core.process import run_command_safe
from harness_bridge.core.types import SessionInfo, TaskResult, TaskSpec, TokenUsage
from harness_bridge.drivers.antigravity import AntigravityDriver
from harness_bridge.drivers.claude import ClaudeCodeDriver
from harness_bridge.server.mcp_server import (
    _session_manager,
    bridge_cancel_session,
    bridge_dispatch_task,
    bridge_get_session,
)
from harness_bridge.session.manager import SessionManager


@pytest.mark.asyncio
async def test_session_mapping_and_disk_persistence(tmp_path: Path):
    """Verify native harness session ID mapping persists to disk and survives server restart."""
    mgr1 = SessionManager(storage_dir=tmp_path)

    # Mock driver that emits native agy conversation ID and token usage
    mock_result = TaskResult(
        session_id="bridge-sess-1",
        harness="agy",
        status="completed",
        output="Codeword remembered: OMEGA",
        harness_session_id="agy-native-conv-999",
        usage=TokenUsage(input_tokens=150, output_tokens=45, total_tokens=195, cost_usd=0.012),
        num_turns=1,
        driver_metadata={"agy_conversation_id": "agy-native-conv-999"},
    )

    with patch("harness_bridge.session.manager.get_driver") as mock_get_driver:
        mock_driver = AsyncMock()
        mock_driver.run_turn.return_value = mock_result
        mock_get_driver.return_value = mock_driver

        spec1 = TaskSpec(
            harness="agy",
            prompt="Remember codeword OMEGA",
            session_id="bridge-sess-1",
            repo_root=str(tmp_path),
        )
        res1 = await mgr1.execute_task(spec1)
        assert res1.harness_session_id == "agy-native-conv-999"
        assert res1.usage is not None
        assert res1.usage.total_tokens == 195

    # Verify session journal exists on disk
    session_file = tmp_path / "bridge-sess-1" / "session.json"
    assert session_file.exists()

    # Simulate server restart with a brand new SessionManager instance
    mgr2 = SessionManager(storage_dir=tmp_path)
    loaded_session = mgr2.get_session("bridge-sess-1")
    assert loaded_session is not None
    assert loaded_session.harness_session_id == "agy-native-conv-999"
    assert loaded_session.turn_count == 1

    # Turn 2: Dispatch turn 2 and assert native harness session ID is passed for resumption
    with patch("harness_bridge.session.manager.get_driver") as mock_get_driver:
        mock_driver = AsyncMock()
        mock_driver.run_turn.return_value = TaskResult(
            session_id="bridge-sess-1",
            harness="agy",
            status="completed",
            output="OMEGA",
            harness_session_id="agy-native-conv-999",
        )
        mock_get_driver.return_value = mock_driver

        spec2 = TaskSpec(
            harness="agy",
            prompt="What was the codeword?",
            session_id="bridge-sess-1",
            repo_root=str(tmp_path),
        )
        await mgr2.execute_task(spec2)

        # Assert task spec received native ID for resume
        invoked_task = mock_driver.run_turn.call_args[0][0]
        assert invoked_task.is_resume is True
        assert invoked_task.harness_session_id == "agy-native-conv-999"


@pytest.mark.asyncio
async def test_claude_driver_json_parsing_and_resume_flag(tmp_path: Path):
    """Verify ClaudeCodeDriver parses native session_id and usage, and passes --resume."""
    driver = ClaudeCodeDriver()
    fake_json_output = (
        '{"type":"result","session_id":"claude-sess-xyz","result":"Hello from Claude",'
        '"usage":{"input_tokens":500,"output_tokens":120},"cost_usd":0.005,"num_turns":2}'
    )

    with patch.object(driver, "resolve_binary", return_value=Path("/usr/bin/claude")):
        with patch("harness_bridge.drivers.claude.run_command_safe") as mock_run:
            mock_run.return_value = (0, fake_json_output, "")

            # Turn 1
            task1 = TaskSpec(harness="claude", prompt="Hi")
            res1 = await driver.run_turn(task1, cwd=tmp_path, env={})
            assert res1.output == "Hello from Claude"
            assert res1.harness_session_id == "claude-sess-xyz"
            assert res1.usage is not None
            assert res1.usage.input_tokens == 500
            assert res1.num_turns == 2

            # Turn 2: Resumption
            task2 = TaskSpec(
                harness="claude",
                prompt="Followup",
                session_id="bridge-uuid",
                harness_session_id="claude-sess-xyz",
                is_resume=True,
            )
            await driver.run_turn(task2, cwd=tmp_path, env={})
            cmd_args = mock_run.call_args[0][0]
            assert "--resume" in cmd_args
            resume_idx = cmd_args.index("--resume")
            assert cmd_args[resume_idx + 1] == "claude-sess-xyz"


@pytest.mark.asyncio
async def test_antigravity_driver_json_parsing_and_conversation_flag(tmp_path: Path):
    """Verify AntigravityDriver parses native conversation_id and passes --conversation."""
    driver = AntigravityDriver()
    fake_json_output = (
        '{"conversation_id":"agy-conv-abc","response":"Task done",'
        '"usage":{"input_tokens":300,"output_tokens":80},"num_turns":1}'
    )

    with patch.object(driver, "resolve_binary", return_value=Path("/usr/bin/agy")):
        with patch("harness_bridge.drivers.antigravity.run_command_safe") as mock_run:
            mock_run.return_value = (0, fake_json_output, "")

            # Turn 1
            task1 = TaskSpec(harness="agy", prompt="Start")
            res1 = await driver.run_turn(task1, cwd=tmp_path, env={})
            assert res1.output == "Task done"
            assert res1.harness_session_id == "agy-conv-abc"
            assert res1.usage is not None
            assert res1.usage.total_tokens == 380

            # Turn 2: Resumption
            task2 = TaskSpec(
                harness="agy",
                prompt="Continue",
                session_id="bridge-uuid",
                harness_session_id="agy-conv-abc",
                is_resume=True,
            )
            await driver.run_turn(task2, cwd=tmp_path, env={})
            cmd_args = mock_run.call_args[0][0]
            assert "--conversation" in cmd_args
            conv_idx = cmd_args.index("--conversation")
            assert cmd_args[conv_idx + 1] == "agy-conv-abc"


@pytest.mark.asyncio
async def test_execution_log_streaming(tmp_path: Path):
    """Verify run_command_safe incrementally streams output to log_path."""
    log_file = tmp_path / "execution.log"
    exit_code, stdout, stderr = await run_command_safe(
        ["python3", "-c", "import sys; print('line 1'); print('line 2')"],
        log_path=log_file,
    )
    assert exit_code == 0
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "line 1" in content
    assert "line 2" in content


@pytest.mark.asyncio
async def test_session_cancellation_and_mcp_cancel(tmp_path: Path):
    """Verify cancelling a session terminates the process group and updates session status."""
    mgr = SessionManager(storage_dir=tmp_path)
    session = SessionInfo(
        session_id="cancel-test-1",
        harness="claude",
        workspace_mode="inherit",
        turn_count=1,
    )
    mgr.sessions["cancel-test-1"] = session

    # Cancel without active pid
    cancelled = await mgr.cancel_session("cancel-test-1")
    assert cancelled is True
    assert session.status == "cancelled"

    # Test MCP tool wrapper
    mcp_res = await bridge_cancel_session("cancel-test-1")
    assert "cancelled" in mcp_res

    # Cancel non-existent session
    assert await mgr.cancel_session("non-existent") is False


@pytest.mark.asyncio
async def test_async_dispatch_and_get_session(tmp_path: Path):
    """Verify bridge_dispatch_task(detach=True) returns immediately and bridge_get_session reflects results."""
    # Temporarily point _session_manager to test storage dir
    orig_storage = _session_manager.storage_dir
    _session_manager.storage_dir = tmp_path

    try:
        with patch.object(_session_manager, "execute_task") as mock_exec:
            mock_exec.return_value = TaskResult(
                session_id="async-sess-1",
                harness="claude",
                status="completed",
                output="Background result ready",
            )

            res = await bridge_dispatch_task(
                harness="claude",
                prompt="Run in background",
                session_id="async-sess-1",
                detach=True,
            )
            assert res["status"] == "running"
            assert res["session_id"] == "async-sess-1"

            # Allow background task to complete
            await asyncio.sleep(0.05)

        # Retrieve session
        sess_details = await bridge_get_session("async-sess-1")
        assert "error" not in sess_details
    finally:
        _session_manager.storage_dir = orig_storage
