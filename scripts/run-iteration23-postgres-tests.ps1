[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# This runner deliberately owns one loopback-only, tmpfs PostgreSQL container.
# It never accepts DATABASE_URL and removes only the exact labelled container.
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runId = [Guid]::NewGuid().ToString("N")
$short = $runId.Substring(0, 12)
$name = "iteration23-pg-$PID-$short"
$label = "com.b2b.iteration23.disposable"
$user = "i23u$short"
$password = "i23p$runId"
$database = "i23d$short"
$containerId = $null

function Require-Ok([int]$Code, [string]$Action) {
    if ($Code -ne 0) { throw "$Action failed with exit code $Code" }
}

try {
    foreach ($command in @("docker", "python")) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Required command is unavailable: $command" }
    }
    if (Test-Path -LiteralPath (Join-Path $repoRoot ".env")) { throw "Refusing repository .env" }
    if (Test-Path -LiteralPath (Join-Path $repoRoot "services\product_api\.env")) { throw "Refusing Product API .env" }
    & docker image inspect postgres:16-alpine | Out-Null; Require-Ok $LASTEXITCODE "Local postgres image preflight"
    $containerId = (& docker run --detach --pull=never --name $name --label "$label=true" --publish "127.0.0.1::5432" --tmpfs "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g" --env "POSTGRES_USER=$user" --env "POSTGRES_PASSWORD=$password" --env "POSTGRES_DB=$database" postgres:16-alpine).Trim()
    Require-Ok $LASTEXITCODE "Disposable PostgreSQL startup"
    if ($containerId -notmatch "^[a-f0-9]{64}$") { throw "Docker did not return a full container ID" }
    $portLine = (& docker port $containerId "5432/tcp").Trim(); Require-Ok $LASTEXITCODE "PostgreSQL port lookup"
    if ($portLine -notmatch "^127\.0\.0\.1:(?<port>[1-9][0-9]{0,4})$") { throw "Disposable PostgreSQL is not loopback-only" }
    $port = $Matches.port
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $containerId pg_isready -U $user -d $database | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($LASTEXITCODE -ne 0) { throw "Disposable PostgreSQL did not become ready" }
    $env:PYTHONPATH = "$(Join-Path $repoRoot 'services\product_api\src')$([IO.Path]::PathSeparator)$repoRoot"
    $env:DATABASE_URL = "postgresql+asyncpg://${user}:${password}@127.0.0.1:${port}/${database}"
    $env:TEST_DATABASE_URL = $env:DATABASE_URL
    Push-Location (Join-Path $repoRoot "services\product_api")
    try {
        & python -m alembic -c alembic.ini upgrade head; Require-Ok $LASTEXITCODE "Alembic upgrade"
    } finally { Pop-Location }
    # The H2 pin is created by the fenced company-card-v2 job finalizer, so
    # run both the presentation lineage and finalization-atomicity suites.
    & python -m pytest services/product_api/tests/test_company_report_presentations.py services/product_api/tests/test_company_report_jobs.py -q
    Require-Ok $LASTEXITCODE "Iteration 23 PostgreSQL tests"
} finally {
    if ($containerId) {
        $labelsRaw = (& docker inspect --format '{{json .Config.Labels}}' $containerId 2>$null).Trim()
        $labels = if ($labelsRaw) { $labelsRaw | ConvertFrom-Json } else { $null }
        $owned = if ($labels) { [string]$labels.PSObject.Properties[$label].Value } else { "" }
        if ($owned -eq "true") { & docker rm --force $containerId | Out-Null }
    }
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
}
