from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from harness_bridge import __version__
from harness_bridge.cli.main import app
from harness_bridge.core.types import TaskResult

runner = CliRunner()


def test_cli_version():
    """Verify version command prints version and platform."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help():
    """Verify top-level help text renders cleanly."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Multi-harness inter-agent communication bus" in result.stdout
    assert "serve" in result.stdout
    assert "list" in result.stdout


def test_cli_list():
    """Verify list command displays supported harnesses table."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Supported Agent Harnesses" in result.stdout
    assert "claude" in result.stdout
    assert "agy" in result.stdout


def test_cli_update_check():
    """Verify update --check flag checks GitHub releases."""
    with patch("harness_bridge.cli.main.check_for_updates") as mock_check:
        mock_check.return_value = (True, "0.0.1", "0.1.0", "https://example.com/whl")
        result = runner.invoke(app, ["update", "--check"])
        assert result.exit_code == 0
        assert "Update available" in result.stdout
        assert "v0.0.1 -> v0.1.0" in result.stdout

    with patch("harness_bridge.cli.main.check_for_updates") as mock_check:
        mock_check.return_value = (False, "0.1.0", "0.1.0", None)
        result = runner.invoke(app, ["update", "--check"])
        assert result.exit_code == 0
        assert "up to date" in result.stdout


def test_cli_update_perform():
    """Verify update execution command."""
    with patch("harness_bridge.cli.main.perform_update", return_value=True) as mock_perform:
        result = runner.invoke(app, ["update"])
        assert result.exit_code == 0
        assert mock_perform.called


def test_cli_reload():
    """Verify reload command terminates running servers."""
    with patch("harness_bridge.cli.main.restart_running_servers", return_value=2):
        result = runner.invoke(app, ["reload"])
        assert result.exit_code == 0
        assert "Successfully reloaded 2" in result.stdout

    with patch("harness_bridge.cli.main.restart_running_servers", return_value=0):
        result = runner.invoke(app, ["reload"])
        assert result.exit_code == 0
        assert "No stale background" in result.stdout


def test_cli_run_command():
    """Verify run command invokes session manager."""
    mock_result = TaskResult(
        session_id="test-run-1",
        harness="claude",
        status="completed",
        output="Result from Claude",
        exit_code=0,
    )
    with patch("harness_bridge.cli.main.SessionManager") as mock_mgr_cls:
        mock_mgr = AsyncMock()
        mock_mgr.execute_task.return_value = mock_result
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["run", "Fix bug in parser", "-t", "claude"])
        assert result.exit_code == 0
        assert "Result from Claude" in result.stdout


def test_cli_test_command():
    """Verify test self-diagnostics command."""
    result = runner.invoke(app, ["test"])
    assert result.exit_code == 0
    assert "Diagnostics" in result.stdout


def test_cli_serve_transports():
    """Verify serve command passes transport, host, and port."""
    with patch("harness_bridge.cli.main.run_server", new_callable=AsyncMock) as mock_run:
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(transport="stdio", host="0.0.0.0", port=8000)

    with patch("harness_bridge.cli.main.run_server", new_callable=AsyncMock) as mock_run:
        result = runner.invoke(
            app, ["serve", "--transport", "sse", "--host", "127.0.0.1", "--port", "9000"]
        )
        assert result.exit_code == 0
        mock_run.assert_called_once_with(transport="sse", host="127.0.0.1", port=9000)

    with patch(
        "harness_bridge.cli.main.run_server", side_effect=ValueError("Unsupported transport")
    ):
        result = runner.invoke(app, ["serve", "--transport", "invalid"])
        assert result.exit_code == 1
        assert "Unsupported transport" in result.output
