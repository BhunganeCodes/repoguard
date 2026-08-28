$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python"
if (Test-Path $venvPython) {
    $python = $venvPython
}
else {
    Write-Host "No virtual environment found. Run .\scripts\setup.ps1 first."
    $python = "python"
}

& $python -m pytest