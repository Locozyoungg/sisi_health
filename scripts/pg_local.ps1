# SISI dev database lifecycle for portable PostgreSQL (no Docker, no admin).
# Usage: .\scripts\pg_local.ps1 <ensure|start|stop|status|init>
param([Parameter(Position = 0)][string]$Action = "ensure")

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bin = Join-Path $Repo ".tools\pgsql\pgsql\bin"
$Data = Join-Path $Repo ".tools\pgdata"
$Log = Join-Path $Repo ".tools\pg.log"

function Pg-Running {
    if (-not (Test-Path (Join-Path $Bin "pg_ctl.exe"))) { return $false }
    & (Join-Path $Bin "pg_ctl.exe") -D $Data status *> $null
    return ($LASTEXITCODE -eq 0)
}

switch ($Action) {
    "init" {
        if (Test-Path $Data) { Write-Host "pgdata already initialized"; exit 0 }
        & (Join-Path $Bin "initdb.exe") -D $Data -U sisi --auth=trust -E UTF8 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "initdb failed" }
        & (Join-Path $Bin "pg_ctl.exe") -D $Data -l $Log start | Out-Null
        & (Join-Path $Bin "createdb.exe") -h localhost -p 5432 -U sisi sisi
        & (Join-Path $Bin "createdb.exe") -h localhost -p 5432 -U sisi sisi_test
        & (Join-Path $Bin "psql.exe") -h localhost -p 5432 -U sisi -d sisi -c "ALTER USER sisi PASSWORD 'sisi_dev_pw';" | Out-Null
        Write-Host "postgres initialized (dbs: sisi, sisi_test; user: sisi)"
    }
    "start" {
        if (-not (Pg-Running)) {
            & (Join-Path $Bin "pg_ctl.exe") -D $Data -l $Log start | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed (run init first)" }
        }
        Write-Host "postgres running on localhost:5432"
    }
    "stop" {
        if (Pg-Running) { & (Join-Path $Bin "pg_ctl.exe") -D $Data stop -m fast | Out-Null }
        Write-Host "postgres stopped"
    }
    "status" {
        if (Pg-Running) { Write-Host "postgres: running" } else { Write-Host "postgres: stopped" }
    }
    "ensure" {
        if (-not (Test-Path $Data)) { & $MyInvocation.MyCommand.Path "init" } else { & $MyInvocation.MyCommand.Path "start" }
    }
    default { Write-Error "Unknown action '$Action' (ensure|start|stop|status|init)" }
}
