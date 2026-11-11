$ErrorActionPreference = "Stop"
$Repo = "sukumar1210/harness-bridge"
$InstallDir = Join-Path $HOME ".harness-bridge"
$VenvDir = Join-Path $InstallDir "venv"
$BinDir = Join-Path $HOME ".local\bin"

Write-Host "=== Installing Harness Bridge ===" -ForegroundColor Cyan

if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null }
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir -Force | Out-Null }

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment in $VenvDir..."
    python -m venv $VenvDir
}

$Pip = Join-Path $VenvDir "Scripts\pip.exe"
Write-Host "Fetching latest release from GitHub..."
try {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
    $Asset = $Release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
    if ($Asset) {
        $TmpWhl = [System.IO.Path]::GetTempFileName() + ".whl"
        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $TmpWhl
        & $Pip install --upgrade --quiet $TmpWhl
        Remove-Item $TmpWhl -Force
    } else {
        & $Pip install --upgrade --quiet "git+https://github.com/$Repo.git"
    }
} catch {
    & $Pip install --upgrade --quiet "git+https://github.com/$Repo.git"
}

# Create wrapper script
$ShimPath = Join-Path $BinDir "harness-bridge.cmd"
"@echo off`n`"$VenvDir\Scripts\harness-bridge.exe`" %*" | Out-File -FilePath $ShimPath -Encoding ascii

Write-Host "=== Harness Bridge installed successfully to $ShimPath ===" -ForegroundColor Green
if ($env:PATH -notlike "*$BinDir*") {
    Write-Host "Note: Please ensure $BinDir is in your PATH." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Next step: Register Harness Bridge in your installed coding harnesses (Claude Code, Antigravity):" -ForegroundColor Cyan
Write-Host "    harness-bridge setup" -ForegroundColor White
Write-Host ""
