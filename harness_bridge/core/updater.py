from __future__ import annotations

import json
import logging
import sys
import tempfile
import time
from pathlib import Path

import httpx
from rich.console import Console

from harness_bridge import __version__
from harness_bridge.core.exceptions import UpdateError
from harness_bridge.core.process import run_command_safe

# Suppress httpx INFO logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_REPO = "sukumar1210/harness-bridge"
CACHE_DIR = Path.home() / ".harness-bridge"
CACHE_FILE = CACHE_DIR / "update_cache.json"
CHECK_INTERVAL_SECONDS = 86400  # 24 hours

err_console = Console(stderr=True)


def parse_semver(v: str) -> tuple[int, ...]:
    """Parse a semantic version string into a numeric tuple for comparison."""
    clean = v.lstrip("v").strip()
    parts = []
    for p in clean.split("."):
        p_clean = p.split("-")[0].split("+")[0]
        try:
            parts.append(int(p_clean))
        except ValueError:
            break
    return tuple(parts) if parts else (0, 0, 0)


async def check_for_updates(
    repo: str = DEFAULT_REPO,
    force: bool = False,
) -> tuple[bool, str, str, str | None]:
    """Check GitHub Releases for an available update.

    Returns:
        (has_update, current_version, latest_version, wheel_url)
    """
    now = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            last_check = cache.get("last_check", 0)
            if now - last_check < CHECK_INTERVAL_SECONDS:
                latest = cache.get("latest_version", __version__)
                wheel = cache.get("wheel_url")
                has_update = parse_semver(latest) > parse_semver(__version__)
                return has_update, __version__, latest, wheel
        except Exception:
            pass

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"harness-bridge/{__version__}",
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                cache_data = {
                    "last_check": now,
                    "latest_version": __version__,
                    "wheel_url": None,
                }
                CACHE_FILE.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
                return False, __version__, __version__, None
            resp.raise_for_status()
            data = resp.json()

        latest_tag = data.get("tag_name", "").lstrip("v").strip()
        if not latest_tag:
            return False, __version__, __version__, None

        wheel_url = None
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(".whl"):
                wheel_url = asset.get("browser_download_url")
                break

        cache_data = {
            "last_check": now,
            "latest_version": latest_tag,
            "wheel_url": wheel_url,
        }
        CACHE_FILE.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")

        has_update = parse_semver(latest_tag) > parse_semver(__version__)
        return has_update, __version__, latest_tag, wheel_url

    except Exception as e:
        if force:
            raise UpdateError(f"Failed to check GitHub releases: {e}") from e
        return False, __version__, __version__, None


async def maybe_notify_update(repo: str = DEFAULT_REPO) -> None:
    """Passively notify the user on stderr if an update is available without blocking stdout."""
    try:
        has_update, current, latest, _ = await check_for_updates(repo, force=False)
        if has_update:
            err_console.print(
                f"[yellow][harness-bridge][/yellow] Update available: v{current} -> v{latest}. "
                "Run 'harness-bridge update' to upgrade."
            )
    except Exception:
        pass


async def perform_update(repo: str = DEFAULT_REPO) -> bool:
    """Download the latest release wheel from GitHub and upgrade the local installation."""
    err_console.print(f"[bold cyan]Checking for updates on {repo}...[/bold cyan]")
    has_update, current, latest, wheel_url = await check_for_updates(repo, force=True)

    if not has_update:
        err_console.print(f"[green]harness-bridge is already up to date (v{current}).[/green]")
        return True

    err_console.print(
        f"[bold yellow]New version available: v{latest} (current: v{current})[/bold yellow]"
    )

    py_exe = Path(sys.executable)
    # Check if we are inside a virtual environment
    venv_pip = py_exe.parent / ("pip.exe" if sys.platform == "win32" else "pip")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        if wheel_url:
            err_console.print(f"Downloading release wheel: {wheel_url}...")
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(wheel_url)
                resp.raise_for_status()
                wheel_file = tmp_path / wheel_url.split("/")[-1]
                wheel_file.write_bytes(resp.content)
            target_install = str(wheel_file)
        else:
            # Fallback to git release tarball
            target_install = f"git+https://github.com/{repo}.git@v{latest}"

        err_console.print("Installing updated package...")
        if venv_pip.exists():
            cmd = [str(venv_pip), "install", "--upgrade", target_install]
        else:
            cmd = [str(py_exe), "-m", "pip", "install", "--upgrade", target_install]

        code, stdout, stderr = await run_command_safe(cmd, timeout=120.0)
        if code != 0:
            raise UpdateError(f"Update installation failed (exit {code}):\n{stderr or stdout}")

    err_console.print(
        f"[bold green]Successfully upgraded harness-bridge to v{latest}![/bold green]"
    )
    return True
