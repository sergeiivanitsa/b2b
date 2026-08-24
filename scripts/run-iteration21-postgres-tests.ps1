[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Targeted", "Full")]
    [string]$Mode
)

# Disposable local PostgreSQL evidence runner.  It deliberately refuses .env
# files and leaves all paid/provider/narrative activation switches closed.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$productRoot = Join-Path $repoRoot "services\product_api"
$gatewayRoot = Join-Path $repoRoot "services\gateway_api"
$runId = [Guid]::NewGuid().ToString("N")
$shortId = $runId.Substring(0, 12)
$containerName = "iteration21-pg-$PID-$shortId"
$labelName = "com.b2b.iteration21.disposable"
$labelRun = "com.b2b.iteration21.run-id"
$junitRoot = Join-Path $repoRoot ".tmp\iteration21-postgres"
$junitPath = Join-Path $junitRoot ($(if ($Mode -eq "Targeted") { "targeted.xml" } else { "full.xml" }))
$pgUser, $pgPassword, $pgDatabase = "i21u$shortId", "i21p$runId", "i21d$shortId"
$claimsUploadDirectory = Join-Path ([IO.Path]::GetTempPath()) "iteration21-claims-$runId"
$containerId = $null
$saved = @{}

function Assert-Exit([string]$Operation) {
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed with exit code $LASTEXITCODE" }
}
function Set-ProcessEnv([string]$Name, [AllowNull()][object]$Value) {
    if ($null -eq $Value) {
        [Environment]::SetEnvironmentVariable($Name, $null, "Process")
        return
    }
    [Environment]::SetEnvironmentVariable($Name, [string]$Value, "Process")
}

$isolate = @(
    "APP_ENV", "GATEWAY_URL", "GATEWAY_SHARED_SECRET", "AUTH_TOKEN_SECRET", "CLAIM_EDIT_TOKEN_SECRET",
    "INVITE_TOKEN_SECRET", "SESSION_SECRET", "EMAIL_FROM", "CLAIMS_PRICE_RUB", "CLAIMS_UPLOAD_DIR",
    "DATABASE_URL", "TEST_DATABASE_URL", "TEST_POSTGRES_ADMIN_URL", "PYTHONPATH", "OPENAI_API_KEY", "DATANEWTON_ENABLED",
    "AI_EXPLANATION_ENABLED", "CLAIMS_FIO_AI_ENABLED",
    "COMPANY_CARD_V2_WRITER_ENABLED", "COMPANY_CARD_V2_PRESENTATIONS_ENABLED", "COMPANY_CARD_V2_ROLLOUT_GENERATION",
    "COMPANY_CARD_V2_ALLOWLIST_INNS", "COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS",
    "COMPANY_CARD_AI_NARRATIVE_ENABLED", "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH", "COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS",
    "COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS", "COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY",
    "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS", "COMPANY_CARD_AI_NARRATIVE_MAX_OUTPUT_TOKENS",
    "COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED", "COMPANY_CARD_NARRATIVE_MODEL_PROFILE", "COMPANY_CARD_NARRATIVE_MODEL"
) + @(
    Get-ChildItem Env: |
        Where-Object {
            $_.Name -like "DATANEWTON_*" -or
            $_.Name -like "AI_EXPLANATION_*" -or
            $_.Name -like "CLAIMS_FIO_AI_*" -or
            $_.Name -like "COMPANY_CARD_V2_*" -or
            $_.Name -like "COMPANY_CARD_AI_*" -or
            $_.Name -like "COMPANY_CARD_NARRATIVE_*"
        } |
        ForEach-Object { $_.Name }
) | Select-Object -Unique

try {
    foreach ($path in @((Join-Path $repoRoot ".env"), (Join-Path $productRoot ".env"))) {
        if (Test-Path -LiteralPath $path) { throw "Refusing unreviewed .env: $path" }
    }
    foreach ($name in $isolate) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
    & docker version --format '{{.Server.Version}}' | Out-Null; Assert-Exit "Docker daemon preflight"
    & docker image inspect postgres:16-alpine --format '{{.Id}}' | Out-Null; Assert-Exit "Local postgres:16-alpine image preflight"
    if (-not (Test-Path -LiteralPath $junitRoot)) { New-Item -ItemType Directory -Path $junitRoot -Force | Out-Null }
    if (Test-Path -LiteralPath $junitPath) { Remove-Item -Force -LiteralPath $junitPath }

    $dockerArgs = @("run", "--detach", "--pull=never", "--name", $containerName, "--label", "$labelName=true", "--label", "$labelRun=$runId", "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g", "--env", "POSTGRES_USER=$pgUser", "--env", "POSTGRES_PASSWORD=$pgPassword", "--env", "POSTGRES_DB=$pgDatabase", "postgres:16-alpine")
    $containerId = ((& docker @dockerArgs) -join "").Trim(); Assert-Exit "Disposable PostgreSQL startup"
    if ($containerId -notmatch "^[a-f0-9]{64}$") { throw "Docker did not return exact container id" }
    $port = ((& docker port $containerId "5432/tcp") -join "").Trim(); Assert-Exit "PostgreSQL port lookup"
    if ($port -notmatch "^127\.0\.0\.1:(?<port>[1-9][0-9]{0,4})$") { throw "PostgreSQL must use a loopback dynamic port" }
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) { & docker exec $containerId pg_isready -U $pgUser -d $pgDatabase *> $null; if ($LASTEXITCODE -eq 0) { $ready = $true; break }; Start-Sleep -Seconds 1 }
    if (-not $ready) { throw "PostgreSQL readiness failed after 60 seconds" }

    $url = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:$($Matches.port)/$pgDatabase"
    Set-ProcessEnv "DATABASE_URL" $url; Set-ProcessEnv "TEST_DATABASE_URL" $url; Set-ProcessEnv "TEST_POSTGRES_ADMIN_URL" "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:$($Matches.port)/postgres"
    Set-ProcessEnv "PYTHONPATH" "$productRoot\src$([IO.Path]::PathSeparator)$repoRoot"
    Set-ProcessEnv "APP_ENV" "dev"; Set-ProcessEnv "GATEWAY_URL" "http://127.0.0.1:9"; Set-ProcessEnv "GATEWAY_SHARED_SECRET" "iteration21-test-gateway-secret"; Set-ProcessEnv "AUTH_TOKEN_SECRET" "iteration21-test-auth-secret"; Set-ProcessEnv "CLAIM_EDIT_TOKEN_SECRET" "iteration21-test-claim-secret"; Set-ProcessEnv "INVITE_TOKEN_SECRET" "iteration21-test-invite-secret"; Set-ProcessEnv "SESSION_SECRET" "iteration21-test-session-secret"; Set-ProcessEnv "EMAIL_FROM" "iteration21-tests@example.com"; Set-ProcessEnv "CLAIMS_PRICE_RUB" "990"; Set-ProcessEnv "CLAIMS_UPLOAD_DIR" $claimsUploadDirectory
    foreach ($name in $isolate) {
        if (
            $name -like "DATANEWTON_*" -or
            $name -like "AI_EXPLANATION_*" -or
            $name -like "CLAIMS_FIO_AI_*" -or
            $name -like "COMPANY_CARD_V2_*" -or
            $name -like "COMPANY_CARD_AI_*" -or
            $name -like "COMPANY_CARD_NARRATIVE_*"
        ) { Set-ProcessEnv $name $null }
    }
    Set-ProcessEnv "OPENAI_API_KEY" $null; Set-ProcessEnv "DATANEWTON_ENABLED" "false"; Set-ProcessEnv "AI_EXPLANATION_ENABLED" "false"; Set-ProcessEnv "CLAIMS_FIO_AI_ENABLED" "false"; Set-ProcessEnv "COMPANY_CARD_V2_WRITER_ENABLED" "false"; Set-ProcessEnv "COMPANY_CARD_V2_PRESENTATIONS_ENABLED" "false"; Set-ProcessEnv "COMPANY_CARD_V2_ROLLOUT_GENERATION" "0"; Set-ProcessEnv "COMPANY_CARD_V2_ALLOWLIST_INNS" ""; Set-ProcessEnv "COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS" "0"
    Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_ENABLED" "false"; Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH" "true"; Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS" "0"; Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS" "0"; Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY" "0"; Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS" "20"; Set-ProcessEnv "COMPANY_CARD_AI_NARRATIVE_MAX_OUTPUT_TOKENS" "600"; Set-ProcessEnv "COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED" "false"; Set-ProcessEnv "COMPANY_CARD_NARRATIVE_MODEL_PROFILE" "company_card_narrative_structured_v1"; Set-ProcessEnv "COMPANY_CARD_NARRATIVE_MODEL" $null
    $importPath = ((& python -c "import product_api; print(product_api.__file__)" ) -join "").Trim()
    if (-not $importPath.StartsWith((Join-Path $productRoot "src"), [StringComparison]::OrdinalIgnoreCase)) { throw "Python imported product_api outside current worktree: $importPath" }
    & python -c "from product_api.settings import Settings; s=Settings(); assert not s.company_card_v2_narrative_enabled and s.company_card_v2_narrative_kill_switch and s.company_card_v2_narrative_daily_limit == 0 and s.company_card_v2_narrative_monthly_limit == 0 and s.company_card_v2_narrative_concurrency == 0"; Assert-Exit "Fail-closed narrative settings proof"
    Set-ProcessEnv "PYTHONPATH" "$gatewayRoot\src$([IO.Path]::PathSeparator)$repoRoot"
    & python -c "from gateway_api.settings import Settings; s=Settings(); assert not s.company_card_narrative_gateway_enabled and s.company_card_narrative_model is None"; Assert-Exit "Fail-closed narrative Gateway settings proof"
    Set-ProcessEnv "PYTHONPATH" "$productRoot\src$([IO.Path]::PathSeparator)$repoRoot"
    Push-Location $productRoot; try { & python -m alembic -c alembic.ini upgrade head; Assert-Exit "Alembic upgrade" } finally { Pop-Location }
    $targets = if ($Mode -eq "Targeted") { @(
        "services/product_api/tests/test_company_card_narrative_migration.py", "services/product_api/tests/test_company_card_narrative_jobs.py", "services/product_api/tests/test_company_card_narrative_budget.py", "services/product_api/tests/test_company_card_narrative_artifacts.py", "services/product_api/tests/test_company_card_narrative_outbox.py", "services/product_api/tests/test_company_card_narrative_reconciler.py", "services/product_api/tests/test_company_report_presentations.py", "services/product_api/tests/test_company_report_public_h2_reads.py", "services/product_api/tests/test_company_report_jobs.py"
    ) } else { @("services/product_api/tests") }
    foreach ($target in $targets) { if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $target))) { throw "Missing required test target: $target" } }
    Push-Location $repoRoot; try { & python -m pytest $targets -q -ra -p no:cacheprovider "--junitxml=$junitPath"; Assert-Exit "$Mode PostgreSQL tests" } finally { Pop-Location }
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
    foreach ($name in $saved.Keys) { Set-ProcessEnv $name $saved[$name] }
}
