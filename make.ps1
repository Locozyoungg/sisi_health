# SISI Health — PowerShell target wrapper (same targets as the Makefile).
# Usage: .\make.ps1 <target>   e.g.  .\make.ps1 demo-phase1
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Repo "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

function Backend-Py([string[]]$PyArgs) {
    Push-Location $Backend
    try { & $Python @PyArgs; if ($LASTEXITCODE -ne 0) { throw "python exited $LASTEXITCODE" } }
    finally { Pop-Location }
}

switch ($Target) {
    "help" {
        Write-Host "Targets: setup db-up db-down migrate seed test coverage demo-phase1 openapi audit-verify lint typecheck phase4-demo phase5-demo phase7-demo ai-setup ai-test ai-demo ai-eval ai-compare clean"
    }
    "setup" {
        py -3.12 -m venv (Join-Path $Backend ".venv")
        & (Join-Path $Backend ".venv\Scripts\python.exe") -m pip install -U pip
        & (Join-Path $Backend ".venv\Scripts\pip.exe") install -e (Join-Path $Backend "[dev]")
    }
    "db-up" {
        docker info *> $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            docker compose -f (Join-Path $Repo "docker-compose.yml") up -d db redis
        } else {
            Write-Host "docker unavailable — using portable PostgreSQL"
            & (Join-Path $Repo "scripts\pg_local.ps1") "ensure"
        }
    }
    "db-local" { & (Join-Path $Repo "scripts\pg_local.ps1") "ensure" }
    "db-down" { docker compose -f (Join-Path $Repo "docker-compose.yml") down }
    "migrate" { Backend-Py @("-m", "alembic", "upgrade", "head") }
    "seed" { Backend-Py @("scripts/seed_demo.py") }
    "test" { Backend-Py @("-m", "pytest") }
    "coverage" { Backend-Py @("-m", "pytest", "--cov=app", "--cov-report=term-missing", "--cov-fail-under=70") }
    "demo-phase1" {
        & $MyInvocation.MyCommand.Path "db-up"
        Backend-Py @("-m", "alembic", "upgrade", "head")
        Backend-Py @("scripts/seed_demo.py")
        Backend-Py @("scripts/demo_phase1.py")
    }
    "openapi" { Backend-Py @("scripts/export_openapi.py") }
    "audit-verify" { Backend-Py @("scripts/verify_audit_chain.py") }
    "lint" { Backend-Py @("-m", "ruff", "check", "app", "tests", "scripts") }
    "typecheck" { Backend-Py @("-m", "mypy", "app") }
    "android-test" { & (Join-Path $Repo "scripts\android.ps1") "testDebugUnitTest" }
    "android-build" { & (Join-Path $Repo "scripts\android.ps1") "assembleDebug" }
    "android-release" { & (Join-Path $Repo "scripts\android.ps1") "assembleRelease" }
    "android-size" {
        & (Join-Path $Repo "scripts\android.ps1") "assembleRelease"
        # Unsigned: signing is human task H1 (Play Console upload key).
        $apk = Join-Path $Repo "mobile\app\build\outputs\apk\release\app-release-unsigned.apk"
        if (Test-Path $apk) {
            $mb = [math]::Round((Get-Item $apk).Length / 1MB, 2)
            Write-Host "APK size: $mb MB (budget: 25 MB)"
            if ($mb -gt 25) { Write-Error "APK over the 25 MB budget" }
        } else { Write-Error "release APK not found" }
    }
    "ussd-setup" {
        Backend-Py @("-m", "pip", "install", "-e", (Join-Path $Repo "ussd-whatsapp[dev]"))
    }
    "ussd-test" {
        Push-Location (Join-Path $Repo "ussd-whatsapp")
        try { & (Join-Path $Repo "backend\.venv\Scripts\python.exe") -m pytest } finally { Pop-Location }
    }
    "ussd-demo" {
        Push-Location (Join-Path $Repo "ussd-whatsapp")
        try { & (Join-Path $Repo "backend\.venv\Scripts\python.exe") scripts/demo_phase3.py } finally { Pop-Location }
    }
    "ai-setup" {
        Backend-Py @("-m", "pip", "install", "-e", (Join-Path $Repo "ai_service[dev]"))
    }
    "ai-test" {
        Push-Location (Join-Path $Repo "ai_service")
        try { & (Join-Path $Repo "backend\.venv\Scripts\python.exe") -m pytest } finally { Pop-Location }
    }
    "ai-demo" {
        Push-Location (Join-Path $Repo "ai_service")
        try { & (Join-Path $Repo "backend\.venv\Scripts\python.exe") scripts/demo_phase6.py } finally { Pop-Location }
    }
    "ai-eval" {
        Push-Location (Join-Path $Repo "ai_service")
        try { & (Join-Path $Repo "backend\.venv\Scripts\python.exe") scripts/eval_guardrails.py } finally { Pop-Location }
    }
    "ai-compare" {
        Push-Location (Join-Path $Repo "ai_service")
        try { & (Join-Path $Repo "backend\.venv\Scripts\python.exe") scripts/eval_compare.py } finally { Pop-Location }
    }
    "web-setup" {
        Push-Location (Join-Path $Repo "web")
        try { npm install; npx playwright install chromium } finally { Pop-Location }
    }
    "web-test" {
        Push-Location (Join-Path $Repo "web")
        try { npm run e2e } finally { Pop-Location }
    }
    "phase4-demo" {
        Backend-Py @("scripts/seed_school_demo.py")
        Push-Location (Join-Path $Repo "web")
        try { npm run e2e } finally { Pop-Location }
    }
    "phase5-demo" {
        # Corridor demo world. Seeding the school demo first keeps the whole web e2e
        # suite (console.spec.ts + corridor.spec.ts) runnable from a fresh database.
        # The backend must already be running on :8000 (not started here).
        Backend-Py @("scripts/seed_school_demo.py")
        Backend-Py @("scripts/seed_corridor_demo.py")
        Push-Location (Join-Path $Repo "web")
        try { npm run e2e } finally { Pop-Location }
    }
    "phase7-demo" {
        # Employer demo world (Phase 7). npm run e2e drives the WHOLE web suite
        # (console + corridor + employer specs), so all three seeds must run,
        # exactly like phase5-demo plus the employer seed. The backend must
        # already be running on :8000 (not started here).
        Backend-Py @("scripts/seed_school_demo.py")
        Backend-Py @("scripts/seed_corridor_demo.py")
        Backend-Py @("scripts/seed_employer_demo.py")
        Push-Location (Join-Path $Repo "web")
        try { npm run e2e } finally { Pop-Location }
    }
    "clean" {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
            (Join-Path $Backend ".venv"), (Join-Path $Backend ".pytest_cache"), `
            (Join-Path $Backend ".mypy_cache"), (Join-Path $Backend ".ruff_cache"), `
            (Join-Path $Backend "htmlcov"), (Join-Path $Backend ".coverage")
    }
    default { Write-Error "Unknown target '$Target'. Run .\make.ps1 help" }
}
