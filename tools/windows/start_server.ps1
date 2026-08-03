$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[CNlottor] Creating Python virtual environment..."
    py -3.11 -m venv .venv
}

Write-Host "[CNlottor] Installing/updating server dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[all]"

Write-Host "[CNlottor] Starting API at http://0.0.0.0:8000"
Write-Host "[CNlottor] Local client address: http://127.0.0.1:8000"
& $Python -m cnlottor.cli serve --host 0.0.0.0 --port 8000
