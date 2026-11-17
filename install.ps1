# ==============================================================================
# Harness Bridge - Unified One-Shot Installer (Windows PowerShell)
#
# Supported execution forms:
#   1. Remote streaming (irm | iex):
#      irm https://raw.githubusercontent.com/sukumar1210/harness-bridge/main/install.ps1 | iex
#   2. Local execution:
#      .\install.ps1 [-Docker | -Local] [-Port <port>]
#
# Self-contained with zero relative script dependencies.
# ==============================================================================
[CmdletBinding()]
param (
    [switch]$Docker,
    [switch]$Local,
    [switch]$Yes,
    [int]$Port = 8000,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host @"
Harness Bridge Unified One-Shot Installer (PowerShell)

Usage:
  .\install.ps1 [options]
  irm https://.../install.ps1 | iex

Options:
  -Docker          Install and run as single persistent Docker container over SSE/HTTP.
                   (Zero host Python requirement).
  -Local           Install local CLI (~/.local/bin/harness-bridge) running via on-demand stdio.
  -Yes             Non-interactive confirmation (uses auto-detected runtime).
  -Port <int>      Daemon port for Docker mode (default: 8000).
  -Help            Display this help message.

Environment Variables:
  HARNESS_BRIDGE_MODE        Set to 'docker' or 'local' to pre-select runtime.
  HARNESS_BRIDGE_WORKSPACE   Workspace directory mounted to /workspace in Docker.
  PORT                       Port number for Docker container daemon (default: 8000).
"@
    exit 0
}

$Repo = "sukumar1210/harness-bridge"
$DockerImage = "sukumar1210/harness-bridge:latest"
$LocalTag = "harness-bridge:latest"

if ($env:PORT) {
    $Port = [int]$env:PORT
}

$Mode = ""
if ($Docker) { $Mode = "docker" }
elseif ($Local) { $Mode = "local" }
elseif ($env:HARNESS_BRIDGE_MODE) {
    $Mode = $env:HARNESS_BRIDGE_MODE.ToLowerInvariant()
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "           Harness Bridge One-Shot Installer                " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Interactive Selection if not specified
if (-not $Mode) {
    $isInteractive = [Environment]::UserInteractive -and (-not $Yes)
    if ($isInteractive) {
        Write-Host ""
        Write-Host "Select installation runtime:"
        Write-Host "  1) Docker container (Recommended - persistent container, zero host Python)"
        Write-Host "  2) Local host install (installs harness-bridge CLI into ~/.local/bin via venv)"
        Write-Host ""
        $choice = Read-Host "Enter choice [1-2] (default: 1)"
        if ($choice -eq "2" -or $choice -eq "local") {
            $Mode = "local"
        } else {
            $Mode = "docker"
        }
    } else {
        Write-Host "Non-interactive environment detected. Probing host runtimes..."
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            Write-Host "  [✓] Docker found. Defaulting to Docker runtime."
            $Mode = "docker"
        } elseif (Get-Command python -ErrorAction SilentlyContinue -or Get-Command python3 -ErrorAction SilentlyContinue) {
            Write-Host "  [✓] Python found on PATH. Defaulting to Local runtime."
            $Mode = "local"
        } else {
            Write-Error "Neither Docker nor Python 3 was found on PATH. Please install Docker or Python 3.11+."
            exit 1
        }
    }
}

# ------------------------------------------------------------------------------
# Branch 1: Docker Runtime Installation
# ------------------------------------------------------------------------------
if ($Mode -eq "docker") {
    Write-Host ""
    Write-Host "=== Installing Harness Bridge (Docker Mode) ===" -ForegroundColor Green

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "'docker' command not found on PATH. Docker is required for container mode."
        exit 1
    }

    Write-Host "[1/3] Pulling and tagging image..."
    try {
        docker pull $DockerImage 2>$null
        docker tag $DockerImage $LocalTag 2>$null
        Write-Host "  [✓] Image ready: $LocalTag"
    } catch {
        Write-Host "  [!] Could not pull $DockerImage. Checking for local image..."
        if (-not (docker image inspect $LocalTag 2>$null)) {
            Write-Error "Unable to pull $DockerImage and local image $LocalTag was not found."
            exit 1
        }
    }

    Write-Host "[2/3] Starting persistent background container..."
    $WorkspaceMount = if ($env:HARNESS_BRIDGE_WORKSPACE) { $env:HARNESS_BRIDGE_WORKSPACE } else { (Get-Location).Path }

    # Idempotent container handling
    $running = docker ps -q -f "name=^/harness-bridge$"
    $exists = docker ps -aq -f "name=^/harness-bridge$"

    if ($running) {
        Write-Host "  Container 'harness-bridge' is already running."
    } elseif ($exists) {
        Write-Host "  Removing stopped container 'harness-bridge'..."
        docker rm -f harness-bridge | Out-Null
        docker run -d `
            --name harness-bridge `
            --restart unless-stopped `
            -p "${Port}:8000" `
            -v "${WorkspaceMount}:/workspace" `
            -v "harness-bridge-data:/home/bridge/.harness-bridge" `
            $LocalTag `
            serve --transport unified --host 0.0.0.0 --port 8000 | Out-Null
    } else {
        docker run -d `
            --name harness-bridge `
            --restart unless-stopped `
            -p "${Port}:8000" `
            -v "${WorkspaceMount}:/workspace" `
            -v "harness-bridge-data:/home/bridge/.harness-bridge" `
            $LocalTag `
            serve --transport unified --host 0.0.0.0 --port 8000 | Out-Null
    }

    Write-Host "[3/3] Verifying container health and registering harnesses..."
    $SseUrl = "http://localhost:${Port}/sse"
    $Healthy = $false
    for ($i = 0; $i -lt 15; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $SseUrl -Method Head -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
                $Healthy = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 1
    }

    if ($Healthy) {
        Write-Host "  [✓] Daemon healthy and listening at $SseUrl"
    } else {
        Write-Host "  [!] Daemon starting up; proceeding with harness registration..."
    }

    # Register into Claude Code
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        claude mcp remove harness-bridge 2>$null | Out-Null
        claude mcp add --transport sse -s user harness-bridge "$SseUrl" 2>$null | Out-Null
        Write-Host "  [✓] Claude Code: Registered at $SseUrl"
    }

    # Register into Antigravity
    if (Get-Command agy -ErrorAction SilentlyContinue) {
        agy mcp remove harness-bridge 2>$null | Out-Null
        agy mcp add harness-bridge "$SseUrl" 2>$null | Out-Null
        Write-Host "  [✓] Antigravity CLI: Registered at $SseUrl"
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  Installation Complete! Harness Bridge Docker daemon is live." -ForegroundColor Green
    Write-Host "  Container : harness-bridge (docker ps)"
    Write-Host "  Endpoint  : $SseUrl"
    Write-Host "============================================================" -ForegroundColor Green
    exit 0
}

# ------------------------------------------------------------------------------
# Branch 2: Local Host CLI Installation
# ------------------------------------------------------------------------------
if ($Mode -eq "local") {
    Write-Host ""
    Write-Host "=== Installing Harness Bridge (Local Host Mode) ===" -ForegroundColor Green

    $PyCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { $null }
    if (-not $PyCmd) {
        Write-Error "Python 3 was not found on PATH. Python 3.11+ is required for local installation."
        exit 1
    }

    $InstallDir = Join-Path $HOME ".harness-bridge"
    $VenvDir = Join-Path $InstallDir "venv"
    $BinDir = Join-Path $HOME ".local\bin"

    New-Item -ItemType Directory -Force -Path $InstallDir, $BinDir | Out-Null

    Write-Host "[1/3] Setting up isolated Python virtual environment..."
    if (-not (Test-Path $VenvDir)) {
        & $PyCmd -m venv $VenvDir
    }

    $VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
    $VenvExe = Join-Path $VenvDir "Scripts\harness-bridge.exe"

    Write-Host "[2/3] Installing Harness Bridge package..."
    if (Test-Path "pyproject.toml") {
        Write-Host "  Installing from local repository checkout..."
        & $VenvPip install --upgrade --quiet -e .
    } else {
        Write-Host "  Installing latest package from repository..."
        & $VenvPip install --upgrade --quiet "git+https://github.com/${Repo}.git"
    }

    # Copy / shim executable into ~/.local/bin
    $LocalExe = Join-Path $BinDir "harness-bridge.exe"
    if (Test-Path $VenvExe) {
        Copy-Item -Path $VenvExe -Destination $LocalExe -Force
        Write-Host "  [✓] Executable placed: $LocalExe"
    }

    Write-Host "[3/3] Registering Harness Bridge in AI agent harnesses (stdio mode)..."
    if (Test-Path $VenvExe) {
        & $VenvExe setup
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  Installation Complete! Local host runtime configured." -ForegroundColor Green
    Write-Host "  Executable : $LocalExe"
    Write-Host "  Transport  : stdio (on-demand child process, zero idle daemon)"
    Write-Host "============================================================" -ForegroundColor Green
    exit 0
}
