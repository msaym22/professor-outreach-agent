# Professor Outreach Agent — PowerShell runner
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== Professor Outreach Agent ===" -ForegroundColor Cyan
Write-Host "Starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# Activate virtualenv if it exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
} else {
    Write-Warning "No venv found — running with system Python"
}

try {
    python agent.py
    Write-Host "=== Run complete ===" -ForegroundColor Green
} catch {
    Write-Error "Agent crashed: $_"
    exit 1
}
