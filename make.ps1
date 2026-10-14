# SISI Health — PowerShell target wrapper (same targets as the Makefile).
# Usage: .\make.ps1 <target>   e.g.  .\make.ps1 demo-phase1
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Repo "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

function Backend-Py([string[]]$Args) {
    Push-Location $Backend
    try { & $Python @Args; if ($LASTEXITCODE -ne 0) { throw "python exited $LASTEXITCODE" } }
    finally { Pop-Location }
}

switch ($Target) {
    "help" {
        Write-Host "Targets: setup db-up db-down migrate seed test coverage demo-phase1 openapi audit-verify lint typecheck clean"
    }
    "setup" {
        py -3.12 -m venv (Join-Path $Backend ".venv")
        & (Join-Path $Backend ".venv\Scripts\python.exe") -m pip install -U pip
        & (Join-Path $Backend ".venv\Scripts\pip.exe") install -e (Join-Path $Backend "[dev]")
    }
    "db-up" {
        docker compose -f (Join-Path $Repo "docker-compose.yml") up -d db redis
        $DbId = docker compose -f (Join-Path $Repo "docker-compose.yml") ps -q db
        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            docker exec $DbId pg_isready -U sisi -d sisi *> $null
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $ready) { throw "postgres not ready after 60s" }
        Write-Host "postgres ready"
    }
    "db-down" { docker compose -f (Join-Path $Repo "docker-compose.yml") down }
    "migrate" { Backend-Py @("-m", "alembic", "upgrade", "head") }
    "seed" { Backend-Py @("scripts/seed_demo.py") }
    "test" { Backend-Py @("-m", "pytest") }
    "coverage" { Backend-Py @("-m", "pytest", "--cov=app", "--cov-report=term-missing", "--cov-fail-under=70") }
    "demo-phase1" {
        Backend-Py @("-m", "alembic", "upgrade", "head")
        Backend-Py @("scripts/seed_demo.py")
        Backend-Py @("scripts/demo_phase1.py")
    }
    "openapi" { Backend-Py @("scripts/export_openapi.py") }
    "audit-verify" { Backend-Py @("scripts/verify_audit_chain.py") }
    "lint" { Backend-Py @("-m", "ruff", "check", "app", "tests", "scripts") }
    "typecheck" { Backend-Py @("-m", "mypy", "app") }
    "clean" {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
            (Join-Path $Backend ".venv"), (Join-Path $Backend ".pytest_cache"), `
            (Join-Path $Backend ".mypy_cache"), (Join-Path $Backend ".ruff_cache"), `
            (Join-Path $Backend "htmlcov"), (Join-Path $Backend ".coverage")
    }
    default { Write-Error "Unknown target '$Target'. Run .\make.ps1 help" }
}
