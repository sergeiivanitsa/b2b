[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Targeted", "Full")]
    [string]$Mode
)

# This runbook intentionally creates its own loopback-only database. It never
# reads a repository .env and it does not connect to a user or production DB.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$runId = [Guid]::NewGuid().ToString("N")
$shortId = $runId.Substring(0, 12)
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$productRoot = Join-Path $repoRoot "services\product_api"
$junitRoot = Join-Path $repoRoot ".tmp\iteration20-postgres"
$junitPath = Join-Path $junitRoot ($(if ($Mode -eq "Targeted") { "targeted.xml" } else { "full.xml" }))
$containerName = "iteration20-pg-$PID-$shortId"
$labelName = "com.b2b.iteration20.disposable"
$labelRun = "com.b2b.iteration20.run-id"
$pgUser = "i20u$shortId"
$pgPassword = "i20p$runId"
$pgDatabase = "i20d$shortId"
$containerId = $null

function Assert-Exit([int]$Code, [string]$Operation) { if ($Code -ne 0) { throw "$Operation failed with exit code $Code" } }
function Set-Env([string]$Name, [AllowNull()][string]$Value) { [Environment]::SetEnvironmentVariable($Name, $Value, "Process") }

$saved = @{}
@("DATABASE_URL", "TEST_DATABASE_URL", "TEST_POSTGRES_ADMIN_URL", "PYTHONPATH", "DATANEWTON_ENABLED", "AI_EXPLANATION_ENABLED", "COMPANY_CARD_V2_PRESENTATIONS_ENABLED", "COMPANY_CARD_V2_WRITER_ENABLED", "COMPANY_CARD_V2_ROLLOUT_GENERATION", "OPENAI_API_KEY") | ForEach-Object {
    $saved[$_] = [Environment]::GetEnvironmentVariable($_, "Process")
}

try {
    foreach ($envFile in @((Join-Path $repoRoot ".env"), (Join-Path $productRoot ".env"))) {
        if (Test-Path -LiteralPath $envFile) { throw "Refusing unreviewed .env: $envFile" }
    }
    & docker version --format '{{.Server.Version}}' | Out-Null; Assert-Exit $LASTEXITCODE "Docker daemon preflight"
    & docker image inspect postgres:16-alpine --format '{{.Id}}' | Out-Null; Assert-Exit $LASTEXITCODE "Local postgres image preflight"
    if (-not (Test-Path -LiteralPath $junitRoot)) { New-Item -ItemType Directory -Path $junitRoot -Force | Out-Null }
    if (Test-Path -LiteralPath $junitPath) { Remove-Item -LiteralPath $junitPath -Force }

    $dockerArgs = @("run", "--detach", "--pull=never", "--name", $containerName, "--label", "$labelName=true", "--label", "$labelRun=$runId", "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g", "--env", "POSTGRES_USER=$pgUser", "--env", "POSTGRES_PASSWORD=$pgPassword", "--env", "POSTGRES_DB=$pgDatabase", "postgres:16-alpine")
    $containerId = ((& docker @dockerArgs) -join "").Trim(); Assert-Exit $LASTEXITCODE "Disposable PostgreSQL startup"
    if ($containerId -notmatch "^[a-f0-9]{64}$") { throw "Docker did not return exact container id" }
    $port = ((& docker port $containerId "5432/tcp") -join "").Trim(); Assert-Exit $LASTEXITCODE "PostgreSQL port lookup"
    if ($port -notmatch "^127\.0\.0\.1:(?<port>[1-9][0-9]{0,4})$") { throw "PostgreSQL must use a loopback dynamic port" }
    $portNumber = $Matches.port
    for ($i = 0; $i -lt 60; $i++) { & docker exec $containerId pg_isready -U $pgUser -d $pgDatabase | Out-Null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep -Seconds 1 }
    & docker exec $containerId pg_isready -U $pgUser -d $pgDatabase | Out-Null; Assert-Exit $LASTEXITCODE "PostgreSQL readiness"

    Set-Env "DATABASE_URL" "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${portNumber}/${pgDatabase}"
    Set-Env "TEST_DATABASE_URL" ([Environment]::GetEnvironmentVariable("DATABASE_URL", "Process"))
    Set-Env "TEST_POSTGRES_ADMIN_URL" "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${portNumber}/postgres"
    Set-Env "PYTHONPATH" "$productRoot\src$([IO.Path]::PathSeparator)$repoRoot"
    Set-Env "DATANEWTON_ENABLED" "false"; Set-Env "AI_EXPLANATION_ENABLED" "false"; Set-Env "OPENAI_API_KEY" $null
    Set-Env "COMPANY_CARD_V2_PRESENTATIONS_ENABLED" "false"; Set-Env "COMPANY_CARD_V2_WRITER_ENABLED" "false"; Set-Env "COMPANY_CARD_V2_ROLLOUT_GENERATION" "0"
    Push-Location $productRoot; try { & python -m alembic -c alembic.ini upgrade head; Assert-Exit $LASTEXITCODE "Alembic upgrade" } finally { Pop-Location }
    # Keep the targeted evidence broad enough to prove the compatibility
    # boundary, not merely the newly-created H2 tables.
    $targets = if ($Mode -eq "Targeted") { @(
        "services/product_api/tests/test_company_card_v2_migration.py",
        "services/product_api/tests/test_company_report_presentations.py",
        "services/product_api/tests/test_company_report_public_h2_reads.py",
        "services/product_api/tests/test_company_report_publications.py",
        "services/product_api/tests/test_company_report_publications_migration.py",
        "services/product_api/tests/test_company_report_public_h1_reads.py",
        "services/product_api/tests/test_company_reports_api.py",
        "services/product_api/tests/test_claims_company_report_handoff.py"
    ) } else { @("services/product_api/tests") }
    foreach ($target in $targets) { if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $target))) { throw "Missing required test target: $target" } }
    Push-Location $repoRoot; try { & python -m pytest $targets -q -ra -p no:cacheprovider "--junitxml=$junitPath"; Assert-Exit $LASTEXITCODE "$Mode PostgreSQL tests" } finally { Pop-Location }
    [xml]$xml = Get-Content -Raw -LiteralPath $junitPath
    $cases = @($xml.SelectNodes("//testcase")); $bad = @($xml.SelectNodes("//failure|//error|//skipped"))
    if ($cases.Count -eq 0 -or $bad.Count -ne 0) { throw "JUnit evidence is not clean" }
    Write-Host "PASS mode=$Mode tests=$($cases.Count) junit=$junitPath"
}
finally {
    if ($containerId) {
        $identity = ((& docker inspect --format '{{.Id}}|{{.Name}}' $containerId) -join "").Trim()
        $labels = ((& docker inspect --format '{{json .Config.Labels}}' $containerId) -join "").Trim() | ConvertFrom-Json
        if ($identity -eq "$containerId|/$containerName" -and $labels.$labelName -eq "true" -and $labels.$labelRun -eq $runId) { & docker rm --force --volumes $containerId | Out-Null }
    }
    foreach ($name in $saved.Keys) { Set-Env $name $saved[$name] }
}
