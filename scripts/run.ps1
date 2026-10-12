$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Run scripts\setup.ps1 first."
}
& ".\.venv\Scripts\python.exe" -m yaotubng.app
if ($LASTEXITCODE -ne 0) { throw "Application failed (exit $LASTEXITCODE)." }
