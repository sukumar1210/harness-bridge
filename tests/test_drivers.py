from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from harness_bridge.core.exceptions import HarnessNotFoundError
from harness_bridge.core.types import TaskSpec
from harness_bridge.drivers.antigravity import AntigravityDriver
from harness_bridge.drivers.claude import ClaudeCodeDriver, _extract_json_payload
from harness_bridge.drivers.registry import get_driver, list_all_harness_info


def test_driver_registry():
    claude = get_driver("claude")
    assert isinstance(claude, ClaudeCodeDriver)
    assert claude.name == "claude"

    agy = get_driver("agy")
    assert isinstance(agy, AntigravityDriver)
    assert agy.name == "agy"

    antigravity_alias = get_driver("antigravity")
    assert antigravity_alias.name == "agy"

    with pytest.raises(HarnessNotFoundError, match="Unknown harness"):
        get_driver("nonexistent_agent")


def test_list_harness_info():
    infos = list_all_harness_info()
    names = [i.name for i in infos]
    assert "claude" in names
    assert "agy" in names


def test_extract_json_payload():
    assert _extract_json_payload("") is None
    assert _extract_json_payload("not json at all") is None
    assert _extract_json_payload('{"key": "value"}') == {"key": "value"}
    # Multi-line with logs before JSON
    multiline = 'Log line 1\nLog line 2\n{"session_id": "123", "result": "ok"}'
    extracted = _extract_json_payload(multiline)
    assert extracted is not None
    assert extracted["session_id"] == "123"


@pytest.mark.asyncio
async def test_driver_binary_not_found(tmp_path: Path):
    claude = ClaudeCodeDriver()
    with patch.object(claude, "resolve_binary", return_value=None):
        with pytest.raises(HarnessNotFoundError):
            await claude.run_turn(TaskSpec(harness="claude", prompt="test"), cwd=tmp_path, env={})

    agy = AntigravityDriver()
    with patch.object(agy, "resolve_binary", return_value=None):
        with pytest.raises(HarnessNotFoundError):
            await agy.run_turn(TaskSpec(harness="agy", prompt="test"), cwd=tmp_path, env={})


@pytest.mark.asyncio
async def test_driver_stderr_fallback_on_failure(tmp_path: Path):
    claude = ClaudeCodeDriver()
    with patch.object(claude, "resolve_binary", return_value=Path("/bin/claude")):
        with patch(
            "harness_bridge.drivers.claude.run_command_safe",
            return_value=(1, "", "Syntax error in input"),
        ):
            result = await claude.run_turn(
                TaskSpec(harness="claude", prompt="test"), cwd=tmp_path, env={}
            )
            assert result.status == "failed"
            assert "Syntax error in input" in result.output
