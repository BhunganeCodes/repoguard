# Set up the RepoGuard development environment.
# Requirements: Python 3.12+
#
# Usage:
#   .\scripts\setup.ps1

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python 3.12+ is required and 'python' must be on PATH."
}

Write-Host "Creating virtual environment..."
python -m venv .venv

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python"
if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment creation failed."
}

Write-Host "Installing project with dev dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e ".[dev]"

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run tests:   .\scripts\test.ps1"
Write-Host "Run the API: .\scripts\run.ps1"