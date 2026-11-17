# ==============================================================================
# Harness Bridge - Idempotent Setup & Re-Registration Script (PowerShell)
#
# Use this script to re-configure or repair Harness Bridge MCP registration
# in installed agent harnesses (Claude Code, Antigravity CLI).
# ==============================================================================
[CmdletBinding()]
param (
    [switch]$Docker,
    [switch]$Local,
    [int]$Port = 8000,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host @"
Harness Bridge Setup Script (PowerShell)

Usage:
  .\setup.ps1 [-Docker | -Local] [-Port <port>]

Options:
  -Docker       Register harnesses against Docker container daemon (http://localhost:8000/sse).
  -Local        Register harnesses using local host CLI (stdio transport).
  -Port <int>   Port for Docker container daemon (default: 8000).
  -Help         Display this help message.
"@
    exit 0
}

$SseUrl = "http://localhost:${Port}/sse"
$UseDocker = $Docker

if (-not $UseDocker -and -not $Local) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $running = docker ps -q -f "name=^/harness-bridge$"
        if ($running) {
            $UseDocker = $true
        }
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "           Harness Bridge Setup & Re-Registration           " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if ($UseDocker) {
    Write-Host "Configuring harnesses for Docker runtime ($SseUrl)..." -ForegroundColor Green

    if (Get-Command claude -ErrorAction SilentlyContinue) {
        claude mcp remove harness-bridge 2>$null | Out-Null
        claude mcp add --transport sse -s user harness-bridge "$SseUrl" 2>$null | Out-Null
        Write-Host "  [✓] Claude Code: Successfully registered at $SseUrl"
    }

    if (Get-Command agy -ErrorAction SilentlyContinue) {
        agy mcp remove harness-bridge 2>$null | Out-Null
        agy mcp add harness-bridge "$SseUrl" 2>$null | Out-Null
        Write-Host "  [✓] Antigravity CLI: Successfully registered at $SseUrl"
    }

    Write-Host ""
    Write-Host "Setup complete (Docker SSE endpoint: $SseUrl)." -ForegroundColor Green
    exit 0
}

Write-Host "Configuring harnesses for local host runtime (stdio transport)..." -ForegroundColor Green
$ExePath = if (Get-Command harness-bridge -ErrorAction SilentlyContinue) { "harness-bridge" } `
           elseif (Test-Path "$HOME\.local\bin\harness-bridge.exe") { "$HOME\.local\bin\harness-bridge.exe" } `
           elseif (Test-Path "$HOME\.harness-bridge\venv\Scripts\harness-bridge.exe") { "$HOME\.harness-bridge\venv\Scripts\harness-bridge.exe" } `
           else { $null }

if ($ExePath) {
    & $ExePath setup
    Write-Host ""
    Write-Host "Setup complete (Local stdio transport)." -ForegroundColor Green
    exit 0
} else {
    Write-Error "harness-bridge CLI executable not found. Please run '.\install.ps1' first to install Harness Bridge."
    exit 1
}
