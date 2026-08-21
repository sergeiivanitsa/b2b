[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Targeted", "Full")]
    [string]$Mode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$postgresImage = "postgres:16-alpine"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$productApiRoot = Join-Path $repoRoot "services\product_api"
$productApiSource = Join-Path $productApiRoot "src\product_api"
$junitRoot = Join-Path $repoRoot ".tmp\iteration17-postgres"
$junitName = if ($Mode -eq "Targeted") { "targeted.xml" } else { "full.xml" }
$junitPath = Join-Path $junitRoot $junitName

$runId = [Guid]::NewGuid().ToString("N")
$shortRunId = $runId.Substring(0, 12)
$containerName = "iteration17-pg-$PID-$shortRunId"
$disposableLabelName = "com.b2b.iteration17.disposable"
$disposableLabelValue = "true"
$runLabelName = "com.b2b.iteration17.run-id"
$pgUser = "i17user$shortRunId"
$pgPassword = "i17pass$([Guid]::NewGuid().ToString('N'))"
$applicationDatabase = "i17db$shortRunId"
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$claimsUploadDirectory = Join-Path $temporaryRoot "iteration17-claims-$runId"

$targetedTests = @(
    "services/product_api/tests/test_company_report_publications.py",
    "services/product_api/tests/test_company_reports_api.py",
    "services/product_api/tests/test_company_report_public_h1_reads.py",
    "services/product_api/tests/test_claims_company_report_handoff.py"
)
[string[]]$testTargets = if ($Mode -eq "Targeted") {
    $targetedTests
}
else {
    @("services/product_api/tests")
}

$requiredFullMigrationCases = @(
    [pscustomobject]@{
        FileMarker = "test_alembic_version_table_bootstrap"
        TestName = "test_fresh_database_bootstrap_upgrade_current_idempotency_and_round_trip"
    },
    [pscustomobject]@{
        FileMarker = "test_alembic_version_table_bootstrap"
        TestName = "test_existing_varchar_32_preserves_revision_and_application_state"
    },
    [pscustomobject]@{
        FileMarker = "test_company_report_jobs_migration"
        TestName = "test_company_report_jobs_upgrade_inspect_and_downgrade"
    },
    [pscustomobject]@{
        FileMarker = "test_company_report_publications_migration"
        TestName = "test_company_report_publications_upgrade_inspect_and_downgrade"
    },
    [pscustomobject]@{
        FileMarker = "test_claims_handoff_migration"
        TestName = "test_claim_handoff_columns_and_constraints_exist"
    }
)

$environmentNames = @(
    "APP_ENV",
    "LOG_LEVEL",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "TEST_POSTGRES_ADMIN_URL",
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_ADDOPTS",
    "GATEWAY_URL",
    "GATEWAY_SHARED_SECRET",
    "OPENAI_API_KEY",
    "AUTH_TOKEN_SECRET",
    "CLAIM_EDIT_TOKEN_SECRET",
    "INVITE_TOKEN_SECRET",
    "SESSION_SECRET",
    "EMAIL_FROM",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_USE_TLS",
    "CLAIMS_PRICE_RUB",
    "CLAIMS_UPLOAD_DIR",
    "CLAIMS_MAX_FILE_SIZE_BYTES",
    "CLAIMS_ALLOWED_UPLOAD_EXTENSIONS",
    "CLAIMS_ALLOWED_UPLOAD_MIME_TYPES",
    "CLAIMS_ADMIN_EMAILS",
    "CLAIMS_FIO_AI_ENABLED",
    "AI_EXPLANATION_ENABLED",
    "DATANEWTON_ENABLED",
    "DATANEWTON_BASE_URL",
    "DATANEWTON_API_KEY",
    "DATANEWTON_COUNTERPARTY_FILTERS",
    "SEO_PUBLIC_ROLLOUT_ENABLED",
    "APP_BASE_URL",
    "SEO_PUBLIC_BASE_URL",
    "SUPERADMIN_EMAIL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB"
)

$savedEnvironment = @{}
foreach ($name in $environmentNames) {
    $exists = Test-Path -LiteralPath "Env:\$name"
    $savedEnvironment[$name] = [pscustomobject]@{
        Exists = $exists
        Value = if ($exists) {
            [Environment]::GetEnvironmentVariable($name, "Process")
        }
        else {
            $null
        }
    }
}

function Set-ProcessEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$Value
    )

    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Assert-LastExitCode {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,
        [Parameter(Mandatory = $true)]
        [string]$Operation
    )

    if ($ExitCode -ne 0) {
        throw "$Operation failed with exit code $ExitCode"
    }
}

function Assert-PlainDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Description is missing: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Description must not be a reparse point: $Path"
    }
}

function Get-VerifiedContainerIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ContainerId
    )

    $rawIdentity = (& docker inspect --format '{{.Id}}|{{.Name}}' $ContainerId)
    $inspectExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $inspectExit -Operation "Docker container ID/name inspection"
    $identityLine = (($rawIdentity -join "`n").Trim())
    $parts = $identityLine.Split("|")
    if ($parts.Count -ne 2) {
        throw "Docker returned an unexpected container identity shape"
    }

    $rawLabels = (& docker inspect --format '{{json .Config.Labels}}' $ContainerId)
    $labelsExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $labelsExit -Operation "Docker container label inspection"
    $labelsText = (($rawLabels -join "`n").Trim())
    try {
        $labels = $labelsText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "Docker returned malformed container label JSON"
    }
    $disposableProperty = $labels.PSObject.Properties[$disposableLabelName]
    $runProperty = $labels.PSObject.Properties[$runLabelName]
    if ($null -eq $disposableProperty -or $null -eq $runProperty) {
        throw "Docker container is missing the required disposable labels"
    }

    return [pscustomobject]@{
        Id = $parts[0]
        Name = $parts[1]
        DisposableLabel = [string]$disposableProperty.Value
        RunLabel = [string]$runProperty.Value
    }
}

function Assert-ExpectedContainerIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Identity,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedId,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedName,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedRunId
    )

    if (
        $Identity.Id -ne $ExpectedId -or
        $Identity.Name -ne "/$ExpectedName" -or
        $Identity.DisposableLabel -ne $disposableLabelValue -or
        $Identity.RunLabel -ne $ExpectedRunId
    ) {
        throw "Container ID, name, or disposable labels do not match this run"
    }
}

function Assert-JUnitEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [bool]$RequireMigrationCases
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "pytest did not create JUnit evidence: $Path"
    }

    [xml]$document = Get-Content -Raw -LiteralPath $Path
    $testCases = @($document.SelectNodes("//testcase"))
    $failures = @($document.SelectNodes("//testcase/failure"))
    $errors = @($document.SelectNodes("//testcase/error"))
    $skips = @($document.SelectNodes("//testcase/skipped"))

    if ($testCases.Count -le 0) {
        throw "JUnit evidence contains no tests"
    }
    if ($failures.Count -ne 0 -or $errors.Count -ne 0 -or $skips.Count -ne 0) {
        throw (
            "JUnit evidence is not clean: tests={0} failures={1} errors={2} skipped={3}" -f
            $testCases.Count,
            $failures.Count,
            $errors.Count,
            $skips.Count
        )
    }

    if ($RequireMigrationCases) {
        foreach ($required in $requiredFullMigrationCases) {
            $matchingCases = @(
                $testCases | Where-Object {
                    $_.GetAttribute("name") -eq $required.TestName -and
                    $_.GetAttribute("classname").Contains($required.FileMarker)
                }
            )
            if ($matchingCases.Count -ne 1) {
                throw (
                    "Required migration test is absent or duplicated: {0}::{1}" -f
                    $required.FileMarker,
                    $required.TestName
                )
            }
        }
    }

    return [pscustomobject]@{
        Tests = $testCases.Count
        Failures = $failures.Count
        Errors = $errors.Count
        Skipped = $skips.Count
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "README.md") -PathType Leaf)) {
    throw "Unable to resolve the repository root from the script location"
}
if (-not (Test-Path -LiteralPath (Join-Path $productApiRoot "alembic.ini") -PathType Leaf)) {
    throw "Product API Alembic configuration is missing"
}

$repoPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$resolvedJunitRoot = [IO.Path]::GetFullPath($junitRoot)
if (-not $resolvedJunitRoot.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "JUnit evidence directory escaped the repository"
}

$temporaryArtifactRoot = Join-Path $repoRoot ".tmp"
if (Test-Path -LiteralPath $temporaryArtifactRoot) {
    Assert-PlainDirectory -Path $temporaryArtifactRoot -Description "Repository temporary directory"
}
if (Test-Path -LiteralPath $junitRoot) {
    Assert-PlainDirectory -Path $junitRoot -Description "Iteration 17 JUnit directory"
}
else {
    New-Item -ItemType Directory -Path $junitRoot -Force | Out-Null
    Assert-PlainDirectory -Path $junitRoot -Description "Iteration 17 JUnit directory"
}
if (Test-Path -LiteralPath $junitPath) {
    $junitItem = Get-Item -LiteralPath $junitPath -Force
    if (($junitItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "JUnit evidence path must not be a reparse point"
    }
    Remove-Item -Force -LiteralPath $junitPath
}

$dockerArgs = @(
    "run",
    "--detach",
    "--pull=never",
    "--name", $containerName,
    "--label", "$disposableLabelName=$disposableLabelValue",
    "--label", "$runLabelName=$runId",
    "--publish", "127.0.0.1::5432",
    "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g",
    "--health-cmd", "pg_isready -U $pgUser -d $applicationDatabase",
    "--health-interval", "1s",
    "--health-timeout", "3s",
    "--health-start-period", "3s",
    "--health-retries", "60",
    "--env", "POSTGRES_USER",
    "--env", "POSTGRES_PASSWORD",
    "--env", "POSTGRES_DB",
    $postgresImage
)

# Static fail-closed checks are intentionally part of the runbook because this
# repository does not have a PowerShell test framework dependency.
if ($runId -notmatch "^[a-f0-9]{32}$") {
    throw "Generated run ID is not label-safe"
}
if ($containerName -notmatch "^iteration17-pg-[0-9]+-[a-f0-9]{12}$") {
    throw "Generated container name is not in the approved namespace"
}
if ($dockerArgs -notcontains "--pull=never") {
    throw "Docker arguments must forbid pulls"
}
if ($dockerArgs -notcontains "127.0.0.1::5432") {
    throw "Docker arguments must use a loopback-only dynamic port"
}
if ($dockerArgs -notcontains "--tmpfs") {
    throw "Docker arguments must use tmpfs"
}
if ($dockerArgs -contains "--volume" -or $dockerArgs -contains "-v") {
    throw "Docker arguments must not attach a volume"
}
if ($Mode -eq "Full" -and ($testTargets.Count -ne 1 -or $testTargets[0] -ne "services/product_api/tests")) {
    throw "Full mode test selection is not exact"
}
if ($Mode -eq "Targeted" -and $testTargets.Count -ne $targetedTests.Count) {
    throw "Targeted mode test selection is incomplete"
}

$containerId = $null
$containerStarted = $false
$primaryFailure = $null
$cleanupProblems = [Collections.Generic.List[string]]::new()
$junitSummary = $null

try {
    foreach ($envFile in @(
        (Join-Path $repoRoot ".env"),
        (Join-Path $productApiRoot ".env")
    )) {
        if (Test-Path -LiteralPath $envFile) {
            throw "Refusing to run while an unreviewed .env file is present: $envFile"
        }
    }

    foreach ($command in @("docker", "python")) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Required command is unavailable: $command"
        }
    }
    foreach ($testTarget in $testTargets) {
        $targetPath = Join-Path $repoRoot $testTarget
        if (-not (Test-Path -LiteralPath $targetPath)) {
            throw "Required $Mode test target is missing: $testTarget"
        }
    }

    Set-ProcessEnvironment -Name "APP_ENV" -Value "dev"
    Set-ProcessEnvironment -Name "LOG_LEVEL" -Value "WARNING"
    Set-ProcessEnvironment -Name "PYTHONPATH" -Value "$($productApiRoot)\src$([IO.Path]::PathSeparator)$repoRoot"
    Set-ProcessEnvironment -Name "PYTHONDONTWRITEBYTECODE" -Value "1"
    Set-ProcessEnvironment -Name "PYTEST_ADDOPTS" -Value $null
    Set-ProcessEnvironment -Name "GATEWAY_URL" -Value "http://127.0.0.1:9"
    Set-ProcessEnvironment -Name "GATEWAY_SHARED_SECRET" -Value "iteration17-test-gateway-secret"
    Set-ProcessEnvironment -Name "OPENAI_API_KEY" -Value $null
    Set-ProcessEnvironment -Name "AUTH_TOKEN_SECRET" -Value "iteration17-test-auth-secret"
    Set-ProcessEnvironment -Name "CLAIM_EDIT_TOKEN_SECRET" -Value "iteration17-test-claim-secret"
    Set-ProcessEnvironment -Name "INVITE_TOKEN_SECRET" -Value "iteration17-test-invite-secret"
    Set-ProcessEnvironment -Name "SESSION_SECRET" -Value "iteration17-test-session-secret"
    Set-ProcessEnvironment -Name "EMAIL_FROM" -Value "iteration17-tests@example.com"
    Set-ProcessEnvironment -Name "SMTP_HOST" -Value "127.0.0.1"
    Set-ProcessEnvironment -Name "SMTP_PORT" -Value "9"
    Set-ProcessEnvironment -Name "SMTP_USER" -Value $null
    Set-ProcessEnvironment -Name "SMTP_PASSWORD" -Value $null
    Set-ProcessEnvironment -Name "SMTP_USE_TLS" -Value "false"
    Set-ProcessEnvironment -Name "CLAIMS_PRICE_RUB" -Value "990"
    Set-ProcessEnvironment -Name "CLAIMS_UPLOAD_DIR" -Value $claimsUploadDirectory
    Set-ProcessEnvironment -Name "CLAIMS_MAX_FILE_SIZE_BYTES" -Value "10485760"
    Set-ProcessEnvironment -Name "CLAIMS_ALLOWED_UPLOAD_EXTENSIONS" -Value '[".pdf",".doc",".docx",".rtf",".jpg",".jpeg",".png"]'
    Set-ProcessEnvironment -Name "CLAIMS_ALLOWED_UPLOAD_MIME_TYPES" -Value '["application/pdf","application/msword","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/rtf","text/rtf","image/jpeg","image/png"]'
    Set-ProcessEnvironment -Name "CLAIMS_ADMIN_EMAILS" -Value '["claims-admin@example.com"]'
    Set-ProcessEnvironment -Name "CLAIMS_FIO_AI_ENABLED" -Value "false"
    Set-ProcessEnvironment -Name "AI_EXPLANATION_ENABLED" -Value "false"
    Set-ProcessEnvironment -Name "DATANEWTON_ENABLED" -Value "false"
    Set-ProcessEnvironment -Name "DATANEWTON_BASE_URL" -Value "http://127.0.0.1:9"
    Set-ProcessEnvironment -Name "DATANEWTON_API_KEY" -Value $null
    Set-ProcessEnvironment -Name "DATANEWTON_COUNTERPARTY_FILTERS" -Value "MANAGER_BLOCK,ADDRESS_BLOCK"
    Set-ProcessEnvironment -Name "SEO_PUBLIC_ROLLOUT_ENABLED" -Value "false"
    Set-ProcessEnvironment -Name "APP_BASE_URL" -Value "http://127.0.0.1:8000"
    Set-ProcessEnvironment -Name "SEO_PUBLIC_BASE_URL" -Value "http://127.0.0.1:8000"
    Set-ProcessEnvironment -Name "SUPERADMIN_EMAIL" -Value $null

    & python -c "import alembic, asyncpg, pytest, sqlalchemy" | Out-Null
    $dependencyExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $dependencyExit -Operation "Python dependency preflight"

    & python -c "import pathlib, sys, product_api; actual=pathlib.Path(product_api.__file__).resolve().parent; expected=pathlib.Path(sys.argv[1]).resolve(); assert actual == expected, (actual, expected)" $productApiSource
    $importExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $importExit -Operation "Worktree import proof"

    & docker version --format '{{.Server.Version}}' | Out-Null
    $dockerVersionExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $dockerVersionExit -Operation "Docker daemon preflight"

    $localImageId = (& docker image inspect --format '{{.Id}}' $postgresImage)
    $imageInspectExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $imageInspectExit -Operation "Local postgres:16-alpine image preflight"
    if ([string]::IsNullOrWhiteSpace(($localImageId -join "").Trim())) {
        throw "Local postgres:16-alpine image has no inspectable ID"
    }

    $nameCollision = @(
        & docker ps -aq --filter "name=^/$containerName$" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    $collisionExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $collisionExit -Operation "Docker name collision preflight"
    if ($nameCollision.Count -ne 0) {
        throw "Generated container name unexpectedly already exists"
    }

    Set-ProcessEnvironment -Name "POSTGRES_USER" -Value $pgUser
    Set-ProcessEnvironment -Name "POSTGRES_PASSWORD" -Value $pgPassword
    Set-ProcessEnvironment -Name "POSTGRES_DB" -Value $applicationDatabase
    $containerOutput = (& docker @dockerArgs)
    $dockerRunExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $dockerRunExit -Operation "Disposable PostgreSQL startup"
    $containerId = (($containerOutput -join "`n").Trim())
    if ($containerId -notmatch "^[a-f0-9]{64}$") {
        throw "Docker did not return an exact full container ID"
    }
    $containerStarted = $true
    Set-ProcessEnvironment -Name "POSTGRES_USER" -Value $null
    Set-ProcessEnvironment -Name "POSTGRES_PASSWORD" -Value $null
    Set-ProcessEnvironment -Name "POSTGRES_DB" -Value $null

    $startedIdentity = Get-VerifiedContainerIdentity -ContainerId $containerId
    Assert-ExpectedContainerIdentity `
        -Identity $startedIdentity `
        -ExpectedId $containerId `
        -ExpectedName $containerName `
        -ExpectedRunId $runId

    $portOutput = @(
        & docker port $containerId "5432/tcp" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    $portExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $portExit -Operation "Docker dynamic port lookup"
    if ($portOutput.Count -ne 1) {
        throw "Docker did not publish exactly one loopback-only PostgreSQL port"
    }
    if ($portOutput[0] -notmatch '^127\.0\.0\.1:(?<Port>[1-9][0-9]{0,4})$') {
        throw "Docker did not publish exactly one loopback-only PostgreSQL port"
    }
    $hostPort = [int]$Matches.Port
    if ($hostPort -gt 65535) {
        throw "Docker returned an invalid PostgreSQL host port"
    }

    $databaseUrl = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${hostPort}/${applicationDatabase}"
    $adminUrl = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${hostPort}/postgres"
    Set-ProcessEnvironment -Name "DATABASE_URL" -Value $databaseUrl
    Set-ProcessEnvironment -Name "TEST_DATABASE_URL" -Value $databaseUrl
    Set-ProcessEnvironment -Name "TEST_POSTGRES_ADMIN_URL" -Value $adminUrl

    & python -c "import os, sys; from sqlalchemy.engine import make_url; d=make_url(os.environ['DATABASE_URL']); t=make_url(os.environ['TEST_DATABASE_URL']); a=make_url(os.environ['TEST_POSTGRES_ADMIN_URL']); port=int(sys.argv[1]); db=sys.argv[2]; user=sys.argv[3]; assert d == t; assert d.drivername == 'postgresql+asyncpg' and d.host == '127.0.0.1' and d.port == port and d.database == db and d.username == user; assert a.drivername == d.drivername and a.host == d.host and a.port == d.port and a.username == d.username and a.password == d.password and a.database == 'postgres'" "$hostPort" $applicationDatabase $pgUser
    $urlProofExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $urlProofExit -Operation "Disposable database URL proof"

    & python -c "from product_api.settings import Settings; s=Settings(); assert s.claims_allowed_upload_extensions == ['.pdf','.doc','.docx','.rtf','.jpg','.jpeg','.png']; assert s.claims_allowed_upload_mime_types == ['application/pdf','application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/rtf','text/rtf','image/jpeg','image/png']; assert s.claims_admin_emails == ['claims-admin@example.com']; assert not s.datanewton_enabled and not s.claims_fio_ai_enabled and not s.ai_explanation_enabled"
    $settingsProofExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $settingsProofExit -Operation "Isolated test settings proof"

    $healthy = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $healthOutput = (& docker inspect --format '{{.State.Health.Status}}' $containerId)
        $healthExit = $LASTEXITCODE
        Assert-LastExitCode -ExitCode $healthExit -Operation "Disposable PostgreSQL health inspection"
        $health = (($healthOutput -join "").Trim())
        if ($health -eq "healthy") {
            $healthy = $true
            break
        }
        if ($health -eq "unhealthy") {
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) {
        throw "Disposable PostgreSQL did not become healthy within 60 seconds"
    }

    & docker exec $containerId pg_isready -U $pgUser -d $applicationDatabase | Out-Null
    $readyExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $readyExit -Operation "Disposable PostgreSQL readiness probe"

    Push-Location -LiteralPath $productApiRoot
    try {
        & python -m alembic -c alembic.ini upgrade head
        $alembicExit = $LASTEXITCODE
        Assert-LastExitCode -ExitCode $alembicExit -Operation "Alembic upgrade head"
    }
    finally {
        Pop-Location
    }

    Push-Location -LiteralPath $repoRoot
    try {
        & python -m pytest @testTargets -q -ra -p no:cacheprovider "--junitxml=$junitPath"
        $pytestExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    $junitSummary = Assert-JUnitEvidence `
        -Path $junitPath `
        -RequireMigrationCases ($Mode -eq "Full")
    Assert-LastExitCode -ExitCode $pytestExit -Operation "$Mode Product API PostgreSQL tests"

    & python -c "import pathlib, sys, product_api; actual=pathlib.Path(product_api.__file__).resolve().parent; expected=pathlib.Path(sys.argv[1]).resolve(); assert actual == expected, (actual, expected)" $productApiSource
    $postRunImportExit = $LASTEXITCODE
    Assert-LastExitCode -ExitCode $postRunImportExit -Operation "Post-run worktree import proof"
}
catch {
    $primaryFailure = $_.Exception.Message.Replace($pgPassword, "<redacted>")
}
finally {
    if ($containerStarted -and -not [string]::IsNullOrWhiteSpace($containerId)) {
        try {
            $matchingIds = @(
                & docker ps -aq --no-trunc --filter "id=$containerId" |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            )
            $lookupExit = $LASTEXITCODE
            Assert-LastExitCode -ExitCode $lookupExit -Operation "Disposable container cleanup lookup"

            if ($matchingIds.Count -gt 1 -or ($matchingIds.Count -eq 1 -and $matchingIds[0] -ne $containerId)) {
                throw "Cleanup lookup did not resolve only the captured container ID"
            }
            if ($matchingIds.Count -eq 1) {
                $cleanupIdentity = Get-VerifiedContainerIdentity -ContainerId $containerId
                Assert-ExpectedContainerIdentity `
                    -Identity $cleanupIdentity `
                    -ExpectedId $containerId `
                    -ExpectedName $containerName `
                    -ExpectedRunId $runId

                & docker rm --force --volumes $containerId | Out-Null
                $removeExit = $LASTEXITCODE
                Assert-LastExitCode -ExitCode $removeExit -Operation "Disposable container removal"

                $remainingIds = @(
                    & docker ps -aq --no-trunc --filter "id=$containerId" |
                        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
                )
                $verifyRemovalExit = $LASTEXITCODE
                Assert-LastExitCode -ExitCode $verifyRemovalExit -Operation "Disposable container removal verification"
                if ($remainingIds.Count -ne 0) {
                    throw "Disposable container remains after cleanup"
                }
            }
        }
        catch {
            $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
        }
    }

    if (Test-Path -LiteralPath $claimsUploadDirectory) {
        try {
            $resolvedClaimsDirectory = (Resolve-Path -LiteralPath $claimsUploadDirectory).Path
            $temporaryPrefix = $temporaryRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            if (
                $resolvedClaimsDirectory -ne [IO.Path]::GetFullPath($claimsUploadDirectory) -or
                -not $resolvedClaimsDirectory.StartsWith($temporaryPrefix, [StringComparison]::OrdinalIgnoreCase) -or
                (Split-Path -Leaf $resolvedClaimsDirectory) -ne "iteration17-claims-$runId"
            ) {
                throw "Claims upload cleanup target failed its exact path check"
            }
            $reparseEntries = @(
                Get-ChildItem -LiteralPath $resolvedClaimsDirectory -Force -Recurse |
                    Where-Object {
                        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
                    }
            )
            $claimsRootItem = Get-Item -LiteralPath $resolvedClaimsDirectory -Force
            if (
                ($claimsRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                $reparseEntries.Count -ne 0
            ) {
                throw "Claims upload cleanup refused a reparse point"
            }
            Remove-Item -Recurse -Force -LiteralPath $resolvedClaimsDirectory
        }
        catch {
            $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
        }
    }

    foreach ($name in $environmentNames) {
        $saved = $savedEnvironment[$name]
        if ($saved.Exists) {
            [Environment]::SetEnvironmentVariable($name, [string]$saved.Value, "Process")
        }
        else {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
        }
    }
}

if ($cleanupProblems.Count -ne 0) {
    $cleanupMessage = $cleanupProblems -join "; "
    if ($null -ne $primaryFailure) {
        throw "Run failed: $primaryFailure. Cleanup also failed: $cleanupMessage"
    }
    throw "Cleanup failed: $cleanupMessage"
}
if ($null -ne $primaryFailure) {
    throw $primaryFailure
}
if ($null -eq $junitSummary) {
    throw "JUnit summary is unexpectedly missing"
}

Write-Host (
    "PASS mode={0} tests={1} failures={2} errors={3} skipped={4} junit={5} cleanup=confirmed" -f
    $Mode,
    $junitSummary.Tests,
    $junitSummary.Failures,
    $junitSummary.Errors,
    $junitSummary.Skipped,
    $junitPath
)
