# SISI Health - one-command staging/prod deploy (Windows mirror of scripts/deploy.sh).
#
#   .\scripts\deploy.ps1 staging
#   .\scripts\deploy.ps1 prod -DryRun
#
# Same steps as the shell script:
#   1. resolves the target environment (argument, else $env:SISI_DEPLOY_ENV)
#   2. loads .env.prod.<env> when present, otherwise .env.prod
#   3. REFUSES to continue if a development flag or a development-default secret is
#      still in place (non-negotiables 3 and 7) or a required secret is empty
#   4. docker compose -f docker-compose.prod.yml --profile <env> up -d --build
#   5. docker compose ... run --rm backend alembic upgrade head
#   6. waits for the backend/gateway/ai health checks, then prints the URLs
#
# -DryRun performs steps 1-3 and prints the commands instead of running them.
# See docs/runbook.md for rollback, backups and incident escalation.
param(
    [Parameter(Position = 0)][string]$DeployEnv = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ComposeFile = "docker-compose.prod.yml"
$RepoCompose = Join-Path $Repo $ComposeFile

if ([string]::IsNullOrWhiteSpace($DeployEnv)) { $DeployEnv = $env:SISI_DEPLOY_ENV }
if ([string]::IsNullOrWhiteSpace($DeployEnv)) {
    Write-Host "[deploy] REFUSING: pass staging|prod (or set SISI_DEPLOY_ENV)." -ForegroundColor Red
    Write-Host "         Nothing was deployed."
    exit 2
}
if ($DeployEnv -notin @("staging", "prod")) {
    Write-Host "[deploy] REFUSING: SISI_DEPLOY_ENV='$DeployEnv' is not staging|prod." -ForegroundColor Red
    exit 2
}
$env:SISI_DEPLOY_ENV = $DeployEnv

function Refuse([string]$Message) {
    Write-Host "[deploy] REFUSING: $Message" -ForegroundColor Red
    Write-Host "         Nothing was deployed. Fix the value in your env file and re-run."
    exit 1
}

# --- 2. environment file ---------------------------------------------------
$EnvFile = Join-Path $Repo ".env.prod.$DeployEnv"
if (-not (Test-Path $EnvFile)) { $EnvFile = Join-Path $Repo ".env.prod" }
if (-not (Test-Path $EnvFile)) {
    Write-Host "[deploy] REFUSING: no .env.prod.$DeployEnv or .env.prod in $Repo." -ForegroundColor Red
    Write-Host "         Copy .env.prod.example and fill every value first."
    exit 2
}

# Plain KEY=value lines only (the same format .env.prod.example uses). Values are
# never printed: they are secrets.
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    $idx = $trimmed.IndexOf("=")
    if ($idx -lt 1) { continue }
    $key = $trimmed.Substring(0, $idx).Trim()
    $value = $trimmed.Substring($idx + 1).Trim()
    if ($value.Length -ge 2) {
        $first = $value.Substring(0, 1)
        $last = $value.Substring($value.Length - 1, 1)
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    Set-Item -Path "Env:$key" -Value $value
}

Write-Host "[deploy] environment: $DeployEnv"
Write-Host "[deploy] env file:    $EnvFile (values not printed)"

# --- 3. safety gates -------------------------------------------------------
if ($env:SISI_ALLOW_UNVALIDATED_RULES -eq "true") {
    Refuse "SISI_ALLOW_UNVALIDATED_RULES=true - unvalidated clinical rules must never run for real users (non-negotiable 3)."
}
if ($env:SISI_OTP_DEV_RETURN -eq "true") {
    Refuse "SISI_OTP_DEV_RETURN=true - returning OTPs in API responses is dev/demo only."
}
foreach ($flag in @("SISI_ALLOW_UNVALIDATED_RULES", "SISI_OTP_DEV_RETURN")) {
    $value = [Environment]::GetEnvironmentVariable($flag)
    if (-not [string]::IsNullOrEmpty($value) -and $value -ne "false") {
        Refuse "$flag='$value' - only 'false' is accepted in staging/prod."
    }
}

$devSecrets = @{
    "SISI_JWT_SECRET"        = "dev-only-secret-change-me-32-bytes-minimum!"
    "SISI_PHONE_PEPPER"      = "dev-only-pepper-change-me"
    "SISI_JITSI_APP_SECRET"  = "dev-only-jitsi-secret-change-me"
    "SISI_AI_INTERNAL_TOKEN" = "dev-only-ai-token-change-me"
}
foreach ($key in $devSecrets.Keys) {
    if ([Environment]::GetEnvironmentVariable($key) -eq $devSecrets[$key]) {
        Refuse "$key is still the development default."
    }
}

$required = @(
    "SISI_DOMAIN", "SISI_DB_PASSWORD", "SISI_JWT_SECRET", "SISI_PHONE_PEPPER",
    "SISI_MASTER_KEY_B64", "SISI_JITSI_APP_SECRET", "SISI_AI_INTERNAL_TOKEN"
)
foreach ($key in $required) {
    if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($key))) {
        Refuse "$key is empty - it is required in staging/prod."
    }
}

# =============================================================================
# The compose invocations. Kept in one place so the dry run and the real run can
# never drift apart.
$ComposeArgs = @("-f", $RepoCompose, "--profile", $DeployEnv)

if ($DryRun) {
    Write-Host "[deploy] DRY RUN - safety gates passed. Would run:"
    Write-Host "  cd $Repo"
    Write-Host "  docker compose $($ComposeArgs -join ' ') up -d --build"
    Write-Host "  docker compose $($ComposeArgs -join ' ') run --rm backend alembic upgrade head"
    Write-Host "  (then wait for health: backend /v1/health, gateway /health, ai /health)"
    Write-Host "[deploy] URLs that would be printed: https://$($env:SISI_DOMAIN)/ , https://$($env:SISI_DOMAIN)/v1/health"
    exit 0
}

Push-Location $Repo
try {
    # --- 4. build and start ------------------------------------------------
    Write-Host "[deploy] building and starting the $DeployEnv stack..."
    & docker compose @ComposeArgs up -d --build
    if ($LASTEXITCODE -ne 0) { throw "compose up failed (exit $LASTEXITCODE)" }

    # --- 5. migrations -----------------------------------------------------
    Write-Host "[deploy] applying migrations (alembic upgrade head)..."
    & docker compose @ComposeArgs run --rm backend alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed (exit $LASTEXITCODE)" }

    # --- 6. health checks --------------------------------------------------
    Write-Host "[deploy] waiting for container health checks (up to 300s)..."
    $services = @("backend", "gateway", "ai")
    $deadline = (Get-Date).AddSeconds(300)
    $pending = ""
    while ((Get-Date) -lt $deadline) {
        $pending = ""
        foreach ($svc in $services) {
            $cid = (& docker compose @ComposeArgs ps -q $svc 2>$null | Out-String).Trim()
            if ([string]::IsNullOrWhiteSpace($cid)) { $pending += " $svc(not-running)"; continue }
            $status = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $cid 2>$null | Out-String).Trim()
            if ($status -ne "healthy" -and $status -ne "running") { $pending += " $svc($status)" }
        }
        if ([string]::IsNullOrWhiteSpace($pending)) { break }
        Start-Sleep -Seconds 5
        Write-Host "[deploy]   waiting:$pending"
    }

    if (-not [string]::IsNullOrWhiteSpace($pending)) {
        Write-Host "[deploy] WARNING: services not healthy after 300s:$pending" -ForegroundColor Red
        Write-Host "[deploy] Inspect with: docker compose $($ComposeArgs -join ' ') ps ; ... logs --tail=100 <service>"
        exit 1
    }

    Write-Host "[deploy] $DeployEnv is up."
    Write-Host "[deploy]   console:      https://$($env:SISI_DOMAIN)/"
    Write-Host "[deploy]   API health:   https://$($env:SISI_DOMAIN)/v1/health"
    Write-Host "[deploy]   edge health:  https://$($env:SISI_DOMAIN)/health"
    Write-Host "[deploy]   rollback:     docker compose $($ComposeArgs -join ' ') down"
}
finally {
    Pop-Location
}
