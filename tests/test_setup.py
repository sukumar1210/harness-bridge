from unittest.mock import AsyncMock, patch

import pytest

from harness_bridge.core.setup import (
    check_agy_configured_fast,
    check_claude_configured_fast,
    setup_agy,
    setup_all_harnesses,
    setup_claude,
)


@pytest.mark.asyncio
async def test_setup_all_harnesses():
    results = await setup_all_harnesses()
    assert isinstance(results, list)
    harnesses = [r.harness for r in results]
    assert "claude" in harnesses
    assert "agy" in harnesses
    for r in results:
        assert r.status in ("configured", "already_configured", "not_installed", "failed")


def test_fast_config_check():
    # Should not throw any exception regardless of local state
    res_claude = check_claude_configured_fast()
    assert isinstance(res_claude, bool)

    res_agy = check_agy_configured_fast()
    assert isinstance(res_agy, bool)


@pytest.mark.asyncio
async def test_setup_claude_mocked():
    with patch("shutil.which", return_value=None):
        res = await setup_claude()
        assert res.status == "not_installed"

    with patch("shutil.which", return_value="/bin/claude"):
        with patch("harness_bridge.core.setup.check_claude_configured_fast", return_value=True):
            res = await setup_claude(force=False)
            assert res.status == "already_configured"

        with patch("harness_bridge.core.setup.check_claude_configured_fast", return_value=False):
            with patch(
                "harness_bridge.core.setup.run_command_safe", new_callable=AsyncMock
            ) as mock_run:
                mock_run.return_value = (0, "Added harness-bridge", "")
                res = await setup_claude(force=False)
                assert res.status == "configured"

        # Test Docker mode registration via SSE URL
        with patch("harness_bridge.core.setup.check_claude_configured_fast", return_value=False):
            with patch(
                "harness_bridge.core.setup.run_command_safe", new_callable=AsyncMock
            ) as mock_run:
                mock_run.return_value = (0, "Added sse harness-bridge", "")
                res = await setup_claude(use_docker=True)
                assert res.status == "configured"
                call_args = mock_run.call_args[0][0]
                assert "claude" in call_args
                assert "http://localhost:8000/sse" in call_args


@pytest.mark.asyncio
async def test_setup_agy_mocked():
    with patch("shutil.which", return_value=None):
        res = await setup_agy()
        assert res.status == "not_installed"

    with patch("shutil.which", return_value="/bin/agy"):
        with patch("harness_bridge.core.setup.check_agy_configured_fast", return_value=True):
            res = await setup_agy(force=False)
            assert res.status == "already_configured"

        with patch("harness_bridge.core.setup.check_agy_configured_fast", return_value=False):
            with patch(
                "harness_bridge.core.setup.run_command_safe", new_callable=AsyncMock
            ) as mock_run:
                mock_run.return_value = (0, "Added mcp server", "")
                res = await setup_agy(force=False)
                assert res.status == "configured"

        # Test Docker mode registration via SSE URL
        with patch("harness_bridge.core.setup.check_agy_configured_fast", return_value=False):
            with patch(
                "harness_bridge.core.setup.run_command_safe", new_callable=AsyncMock
            ) as mock_run:
                mock_run.return_value = (0, "Added sse agy server", "")
                res = await setup_agy(use_docker=True)
                assert res.status == "configured"
                call_args = mock_run.call_args[0][0]
                assert "agy" in call_args
                assert "http://localhost:8000/sse" in call_args
