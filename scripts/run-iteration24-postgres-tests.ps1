[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# This runner owns one loopback-only, tmpfs PostgreSQL container and exactly
# two databases inside it. It does not accept an external database target and
# never pulls an image or reads repository environment files.
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runId = [Guid]::NewGuid().ToString("N")
$short = $runId.Substring(0, 12)
$name = "iteration24-pg-$PID-$short"
$label = "com.b2b.iteration24.disposable"
$user = "i24u$short"
$password = "i24p$runId"
$guardDatabase = "i24_guard_$short"
$roundtripDatabase = "i24_roundtrip_$short"
$containerId = $null

function Require-Ok([int]$Code, [string]$Action) {
    if ($Code -ne 0) { throw "$Action failed with exit code $Code" }
}

function Assert-OwnedDatabaseName([string]$Database, [string]$ExpectedPrefix) {
    if ($Database -notmatch "^$([regex]::Escape($ExpectedPrefix))[0-9a-f]{12}$") {
        throw "Refusing unknown PostgreSQL database target"
    }
}

try {
    foreach ($command in @("docker", "python")) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Required command is unavailable: $command"
        }
    }
    foreach ($variable in @(
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "TEST_POSTGRES_GUARD_URL",
        "TEST_POSTGRES_ROUNDTRIP_URL"
    )) {
        if (Test-Path -LiteralPath "Env:$variable") {
            throw "Refusing inherited database target: $variable"
        }
    }
    foreach ($environmentFile in @(
        (Join-Path $repoRoot ".env"),
        (Join-Path $repoRoot "services\product_api\.env")
    )) {
        if (Test-Path -LiteralPath $environmentFile) {
            throw "Refusing repository environment file: $environmentFile"
        }
    }
    Assert-OwnedDatabaseName $guardDatabase "i24_guard_"
    Assert-OwnedDatabaseName $roundtripDatabase "i24_roundtrip_"

    & docker image inspect postgres:16-alpine | Out-Null
    Require-Ok $LASTEXITCODE "Local postgres image preflight"
    $containerId = (& docker run --detach --pull=never --name $name `
        --label "$label=true" `
        --publish "127.0.0.1::5432" `
        --tmpfs "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g" `
        --env "POSTGRES_USER=$user" `
        --env "POSTGRES_PASSWORD=$password" `
        --env "POSTGRES_DB=postgres" `
        postgres:16-alpine).Trim()
    Require-Ok $LASTEXITCODE "Disposable PostgreSQL startup"
    if ($containerId -notmatch "^[a-f0-9]{64}$") {
        throw "Docker did not return a full container ID"
    }

    $portLine = (& docker port $containerId "5432/tcp").Trim()
    Require-Ok $LASTEXITCODE "PostgreSQL port lookup"
    if ($portLine -notmatch "^127\.0\.0\.1:(?<port>[1-9][0-9]{0,4})$") {
        throw "Disposable PostgreSQL is not loopback-only"
    }
    $port = $Matches.port
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        & docker exec $containerId pg_isready -U $user -d postgres | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Disposable PostgreSQL did not become ready"
    }

    foreach ($database in @($guardDatabase, $roundtripDatabase)) {
        & docker exec $containerId createdb --username $user --owner $user $database
        Require-Ok $LASTEXITCODE "Create runner-owned database $database"
    }

    $guardUrl = "postgresql+asyncpg://${user}:${password}@127.0.0.1:${port}/${guardDatabase}"
    $roundtripUrl = "postgresql+asyncpg://${user}:${password}@127.0.0.1:${port}/${roundtripDatabase}"
    $env:PYTHONPATH = "$(Join-Path $repoRoot 'services\product_api\src')$([IO.Path]::PathSeparator)$repoRoot"
    $env:DATABASE_URL = $roundtripUrl
    $env:TEST_DATABASE_URL = $roundtripUrl
    $env:TEST_POSTGRES_GUARD_URL = $guardUrl
    $env:TEST_POSTGRES_ROUNDTRIP_URL = $roundtripUrl

    Push-Location $repoRoot
    try {
        & python -m pytest `
            services/product_api/tests/test_company_report_iteration24_migration.py `
            -q -ra -p no:cacheprovider
        Require-Ok $LASTEXITCODE "Iteration 24 migration acceptance tests"

        $integrationTargets = @(
            "services/product_api/tests/test_company_report_jobs.py",
            "services/product_api/tests/test_company_report_presentations.py",
            "services/product_api/tests/test_company_report_public_h2_reads.py",
            "services/product_api/tests/test_company_card_narrative_artifacts.py",
            "services/product_api/tests/test_company_card_narrative_budget.py",
            "services/product_api/tests/test_company_card_narrative_jobs.py",
            "services/product_api/tests/test_company_card_narrative_outbox.py",
            "services/product_api/tests/test_company_card_narrative_reconciler.py",
            "services/product_api/tests/test_claims_company_report_handoff.py"
        )
        & python -m pytest $integrationTargets -q -ra -p no:cacheprovider
        Require-Ok $LASTEXITCODE "Iteration 24 affected PostgreSQL integration tests"
    } finally {
        Pop-Location
    }
} finally {
    if ($containerId -and $containerId -match "^[a-f0-9]{64}$") {
        $labelsRaw = (& docker inspect --format '{{json .Config.Labels}}' $containerId 2>$null).Trim()
        $labels = if ($labelsRaw) { $labelsRaw | ConvertFrom-Json } else { $null }
        $owned = if ($labels) { [string]$labels.PSObject.Properties[$label].Value } else { "" }
        if ($owned -eq "true") {
            foreach ($database in @($guardDatabase, $roundtripDatabase)) {
                Assert-OwnedDatabaseName $database $(if ($database -eq $guardDatabase) { "i24_guard_" } else { "i24_roundtrip_" })
                & docker exec $containerId dropdb --if-exists --maintenance-db=postgres --username $user $database | Out-Null
            }
            & docker rm --force $containerId | Out-Null
        }
    }
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_POSTGRES_GUARD_URL -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_POSTGRES_ROUNDTRIP_URL -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
