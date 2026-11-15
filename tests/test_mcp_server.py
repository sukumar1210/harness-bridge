from __future__ import annotations

from unittest.mock import patch

import pytest

from harness_bridge.core.types import ApplyResult, TaskResult
from harness_bridge.server.mcp_server import (
    _session_manager,
    bridge_apply_diff,
    bridge_cancel_session,
    bridge_close_session,
    bridge_dispatch_task,
    bridge_get_session,
    bridge_list_harnesses,
    mcp_app,
)


@pytest.mark.asyncio
async def test_mcp_list_harnesses_tool():
    """Verify bridge_list_harnesses returns registered harness list."""
    tools = await bridge_list_harnesses()
    assert isinstance(tools, list)
    names = [t["name"] for t in tools]
    assert "claude" in names
    assert "agy" in names


@pytest.mark.asyncio
async def test_mcp_tool_annotations():
    """Verify all MCP tools declare standard ToolAnnotations for M8ven trust compliance."""
    tools = await mcp_app.list_tools()
    tool_map = {t.name: t for t in tools}

    # Verify all 6 core tools exist
    expected_tools = [
        "bridge_list_harnesses",
        "bridge_dispatch_task",
        "bridge_cancel_session",
        "bridge_apply_diff",
        "bridge_get_session",
        "bridge_close_session",
    ]
    for name in expected_tools:
        assert name in tool_map, f"Missing expected tool: {name}"
        ann = tool_map[name].annotations
        assert ann is not None, f"Tool {name} lacks annotations"
        assert ann.read_only_hint is not None
        assert ann.destructive_hint is not None
        assert ann.idempotent_hint is not None
        assert ann.open_world_hint is not None

    # Verify specific annotation flags
    assert tool_map["bridge_list_harnesses"].annotations.read_only_hint is True
    assert tool_map["bridge_get_session"].annotations.read_only_hint is True
    assert tool_map["bridge_cancel_session"].annotations.destructive_hint is True
    assert tool_map["bridge_close_session"].annotations.destructive_hint is True
    assert tool_map["bridge_dispatch_task"].annotations.open_world_hint is True


@pytest.mark.asyncio
async def test_mcp_apply_diff_and_close_session():
    """Verify bridge_apply_diff and bridge_close_session tool wrappers."""
    mock_apply = ApplyResult(
        session_id="sess-123",
        success=True,
        message="Applied 1 change",
        applied_files=["main.py"],
    )
    with patch.object(_session_manager.workspace_manager, "apply_diff", return_value=mock_apply):
        res = await bridge_apply_diff("sess-123")
        assert res["success"] is True
        assert res["applied_files"] == ["main.py"]

    with patch.object(_session_manager, "close_session", return_value=True):
        close_res = await bridge_close_session("sess-123")
        assert close_res["closed"] is True


@pytest.mark.asyncio
async def test_mcp_get_session_not_found():
    """Verify bridge_get_session returns error dict when session does not exist."""
    res = await bridge_get_session("nonexistent-id-999")
    assert "error" in res
    assert "nonexistent-id-999" in res["error"]


@pytest.mark.asyncio
async def test_mcp_dispatch_and_cancel():
    """Verify dispatch task and cancel tool calls."""
    mock_result = TaskResult(
        session_id="test-disp-1",
        harness="claude",
        status="completed",
        output="Done",
    )
    with patch.object(_session_manager, "execute_task", return_value=mock_result):
        res = await bridge_dispatch_task("claude", "fix code", session_id="test-disp-1")
        assert res["status"] == "completed"
        assert res["output"] == "Done"

    with patch.object(_session_manager, "cancel_session", return_value=True):
        cancel_res = await bridge_cancel_session("test-disp-1")
        assert cancel_res["cancelled"] is True
