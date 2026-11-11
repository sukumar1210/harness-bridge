from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from harness_bridge import __version__
from harness_bridge.core.types import TaskSpec, WorkspaceMode
from harness_bridge.core.updater import check_for_updates, maybe_notify_update, perform_update
from harness_bridge.drivers.registry import list_all_harness_info
from harness_bridge.server.mcp_server import run_server
from harness_bridge.session.manager import SessionManager

app = typer.Typer(
    name="harness-bridge",
    help="Multi-harness inter-agent communication bus and MCP server for AI coding agents.",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


@app.callback()
def main_callback(ctx: typer.Context) -> None:
    """Pre-run hook: check for updates passively if not running 'serve' (to keep MCP stdout clean)."""
    if ctx.invoked_subcommand != "serve":
        try:
            asyncio.run(maybe_notify_update())
        except Exception:
            pass


@app.command(name="serve")
def serve_command() -> None:
    """Start the Model Context Protocol (MCP) server over standard I/O (stdio)."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        err_console.print("[yellow]MCP server stopped by user.[/yellow]")


@app.command(name="list")
def list_command() -> None:
    """List supported AI agent harnesses and their detection status on system PATH."""
    harnesses = list_all_harness_info()

    table = Table(title="Supported Agent Harnesses", header_style="bold cyan")
    table.add_column("Harness", style="bold")
    table.add_column("CLI Binary")
    table.add_column("Status")
    table.add_column("Resolved Path")

    for h in harnesses:
        status = "[green]✓ Installed[/green]" if h.installed else "[red]✗ Not Found[/red]"
        table.add_row(
            h.name,
            h.binary,
            status,
            h.path or "[dim]N/A[/dim]",
        )

    console.print(table)


@app.command(name="version")
def version_command() -> None:
    """Display Harness Bridge version, Python runtime, and host OS information."""
    console.print(
        f"[bold cyan]Harness Bridge[/bold cyan] v{__version__}\n"
        f"Python: {platform.python_version()} ({sys.executable})\n"
        f"Platform: {platform.system()} {platform.release()} ({platform.machine()})"
    )


@app.command(name="update")
def update_command(
    check: bool = typer.Option(
        False, "--check", "-c", help="Check for available updates without installing."
    ),
    repo: str = typer.Option(
        "sukumar1210/harness-bridge", "--repo", "-r", help="Target GitHub repository."
    ),
) -> None:
    """Check for new releases on GitHub and self-update the local installation."""
    if check:
        has_update, current, latest, _ = asyncio.run(check_for_updates(repo, force=True))
        if has_update:
            console.print(
                f"[bold yellow]Update available:[/bold yellow] v{current} -> [bold green]v{latest}[/bold green]"
            )
            console.print("Run [bold cyan]harness-bridge update[/bold cyan] to install.")
        else:
            console.print(f"[green]harness-bridge is up to date (v{current}).[/green]")
    else:
        success = asyncio.run(perform_update(repo))
        if not success:
            raise typer.Exit(code=1)


@app.command(name="run")
def run_task_command(
    prompt: str = typer.Argument(..., help="Prompt or task instructions to dispatch."),
    target: str = typer.Option(
        ..., "--target", "-t", help="Target harness name (e.g. 'claude', 'agy')."
    ),
    workspace: str = typer.Option(
        "worktree", "--workspace", "-w", help="Workspace mode ('worktree' or 'inherit')."
    ),
    session_id: Optional[str] = typer.Option(
        None, "--session-id", "-s", help="Existing session ID to resume."
    ),
    timeout: int = typer.Option(300, "--timeout", help="Execution timeout in seconds."),
    repo_root: Optional[Path] = typer.Option(
        None, "--repo-root", help="Path to repository root (defaults to CWD)."
    ),
) -> None:
    """Dispatch a task turn to a target AI harness."""
    mode: WorkspaceMode = "worktree" if workspace == "worktree" else "inherit"
    spec = TaskSpec(
        harness=target,
        prompt=prompt,
        session_id=session_id,
        workspace_mode=mode,
        timeout_seconds=timeout,
        repo_root=str(repo_root.resolve()) if repo_root else str(Path.cwd().resolve()),
    )

    manager = SessionManager()
    with console.status(f"[bold cyan]Dispatching turn to {target}...[/bold cyan]"):
        result = asyncio.run(manager.execute_task(spec))

    status_color = "green" if result.status == "completed" else "red"
    console.print(
        Panel(
            f"[bold]Session ID:[/bold] {result.session_id}\n"
            f"[bold]Status:[/bold] [{status_color}]{result.status}[/{status_color}]\n"
            f"[bold]Duration:[/bold] {result.duration_seconds}s\n"
            f"[bold]Exit Code:[/bold] {result.exit_code}\n\n"
            f"[bold]Output:[/bold]\n{result.output}",
            title=f"Task Result ({result.harness})",
            border_style=status_color,
        )
    )

    if result.diff:
        console.print(
            Panel(
                result.diff,
                title="Generated Git Diff (from isolated worktree)",
                border_style="yellow",
            )
        )


@app.command(name="test")
def test_command() -> None:
    """Run local self-diagnostics verifying driver discovery and git worktree isolation."""
    console.print("[bold cyan]Running Harness Bridge self-diagnostics...[/bold cyan]")

    harnesses = list_all_harness_info()
    found = [h.name for h in harnesses if h.installed]
    if found:
        console.print(f"[green]✓ Detected installed harnesses:[/green] {', '.join(found)}")
    else:
        console.print(
            "[yellow]! No supported harnesses currently installed on system PATH.[/yellow]"
        )

    # Check git repository
    is_git = (Path.cwd() / ".git").exists()
    if is_git:
        console.print("[green]✓ Current directory is a valid git repository.[/green]")
    else:
        console.print("[yellow]! Current directory is not a git repository.[/yellow]")

    console.print("[bold green]Diagnostics complete.[/bold green]")


@app.command(name="setup")
def setup_command(
    executable: Optional[str] = typer.Option(
        None, "--executable", "-e", help="Custom executable command or path for harness-bridge."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-registration even if already configured."
    ),
) -> None:
    """One-shot setup: auto-detect all installed agent harnesses and register Harness Bridge as an MCP server."""
    from harness_bridge.core.setup import setup_all_harnesses

    console.print(
        "[bold cyan]Running one-shot setup for installed AI agent harnesses...[/bold cyan]"
    )
    results = asyncio.run(setup_all_harnesses(executable=executable, force=force))

    table = Table(title="Harness MCP Setup Status", header_style="bold cyan")
    table.add_column("Harness", style="bold")
    table.add_column("Binary")
    table.add_column("Status")
    table.add_column("Details")

    for res in results:
        if res.status == "configured":
            status_str = "[bold green]✓ Configured[/bold green]"
        elif res.status == "already_configured":
            status_str = "[green]✓ Already Registered[/green]"
        elif res.status == "not_installed":
            status_str = "[dim yellow]⚠ Not Installed[/dim yellow]"
        else:
            status_str = "[bold red]✗ Failed[/bold red]"

        table.add_row(res.harness, res.binary, status_str, res.message)

    console.print(table)


if __name__ == "__main__":
    app()
