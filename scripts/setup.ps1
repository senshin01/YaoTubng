$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE)." }
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Checked "py" @("-3.12", "-m", "venv", ".venv")
}
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "requirements.lock")
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "--no-deps", "-e", ".[dev]")
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "yaotubng.cli", "doctor")
Write-Host "Ready. Run: .\scripts\run.ps1"
