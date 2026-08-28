$ErrorActionPreference = "Stop"

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

    python -m uvicorn repoguard.main:app `
        --host 127.0.0.1 `
        --port 8000 `
        --reload
}