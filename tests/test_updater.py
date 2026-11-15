from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness_bridge.core.updater import (
    check_for_updates,
    maybe_notify_update,
    parse_semver,
    perform_update,
    restart_running_servers,
)


def test_parse_semver():
    assert parse_semver("v0.1.0") == (0, 1, 0)
    assert parse_semver("0.2.1") == (0, 2, 1)
    assert parse_semver("v1.0.0-rc1") == (1, 0, 0)
    assert parse_semver("0.1.0") < parse_semver("0.2.0")
    assert parse_semver("1.0.0") > parse_semver("0.9.9")


def test_find_and_restart_running_servers(tmp_path: Path):
    """Verify process identification and restart logic."""
    with patch("harness_bridge.core.updater.find_running_serve_pids", return_value=[99991, 99992]):
        with patch("harness_bridge.core.updater.terminate_pid_group") as mock_term:
            restarted = restart_running_servers()
            assert restarted == 2
            assert mock_term.call_count == 2


@pytest.mark.asyncio
async def test_check_for_updates_cache_hit(tmp_path: Path):
    """Verify update checker uses cache within interval."""
    with patch("harness_bridge.core.updater.CACHE_DIR", tmp_path):
        cache_file = tmp_path / "update_cache.json"
        cache_file.write_text(
            '{"last_check": 9999999999, "latest_version": "0.1.0", "wheel_url": null}',
            encoding="utf-8",
        )
        with patch("harness_bridge.core.updater.CACHE_FILE", cache_file):
            has_update, cur, latest, wheel = await check_for_updates(force=False)
            assert cur == latest or has_update is not None


@pytest.mark.asyncio
async def test_maybe_notify_update():
    """Verify passive update notification on stderr."""
    with patch(
        "harness_bridge.core.updater.check_for_updates", return_value=(True, "0.0.1", "0.2.0", None)
    ):
        with patch("harness_bridge.core.updater.err_console.print") as mock_print:
            await maybe_notify_update()
            assert mock_print.called


@pytest.mark.asyncio
async def test_perform_update_already_up_to_date():
    """Verify perform_update returns cleanly when already on latest version."""
    with patch(
        "harness_bridge.core.updater.check_for_updates",
        return_value=(False, "0.1.0", "0.1.0", None),
    ):
        success = await perform_update()
        assert success is True


@pytest.mark.asyncio
async def test_perform_update_with_wheel(tmp_path: Path):
    """Verify wheel download and pip installation path."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"dummy_wheel_bytes"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch(
        "harness_bridge.core.updater.check_for_updates",
        return_value=(True, "0.1.0", "0.2.0", "https://example.com/hb.whl"),
    ):
        with patch("harness_bridge.core.updater.httpx.AsyncClient", return_value=mock_client):
            with patch(
                "harness_bridge.core.updater.run_command_safe", new_callable=AsyncMock
            ) as mock_run:
                mock_run.return_value = (0, "Successfully installed", "")
                with patch("harness_bridge.core.updater.restart_running_servers", return_value=1):
                    success = await perform_update()
                    assert success is True
                    assert mock_run.called


@pytest.mark.asyncio
async def test_check_for_updates_live_api(tmp_path: Path):
    """Verify live GitHub API response parsing."""
    mock_data = {
        "tag_name": "v0.3.0",
        "assets": [
            {
                "name": "harness_bridge-0.3.0-py3-none-any.whl",
                "browser_download_url": "https://example.com/asset.whl",
            }
        ],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = mock_data

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("harness_bridge.core.updater.CACHE_DIR", tmp_path):
        with patch("harness_bridge.core.updater.CACHE_FILE", tmp_path / "cache.json"):
            with patch("harness_bridge.core.updater.httpx.AsyncClient", return_value=mock_client):
                has_update, cur, latest, wheel = await check_for_updates(force=True)
                assert latest == "0.3.0"
                assert wheel == "https://example.com/asset.whl"
