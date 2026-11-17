# Forwarding shim: redirects to top-level install.ps1
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetScript = Join-Path (Split-Path -Parent $ScriptDir) "install.ps1"
& $TargetScript @args
