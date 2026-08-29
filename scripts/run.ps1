$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$dockerAvailable = $false

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker info *> $null

    if ($LASTEXITCODE -eq 0) {
        $dockerAvailable = $true
    }
}

if ($dockerAvailable) {
    Write-Host "Docker detected. Starting RepoGuard with Docker Compose..."
    docker compose up --build
}
else {
    Write-Host "Docker unavailable. Starting RepoGuard locally..."

    $venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python"
    if (Test-Path $venvPython) {
        $python = $venvPython
    }
    else {
        Write-Host "No virtual environment found. Run .\scripts\setup.ps1 first."
        $python = "python"
    }

    & $python -m uvicorn repoguard.main:app `
        --host 127.0.0.1 `
        --port 8000 `
        --reload
}