[CmdletBinding()]
param(
    [ValidateSet("PostgresFull", "BrowserE2E")]
    [string]$Mode = "PostgresFull",
    [string]$ReleaseArtifactRoot,
    [string]$PlaywrightImage,
    [string]$FontInventory,
    [string]$ReleaseSha,
    [switch]$UpdateSnapshots
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Iteration 25 owns one loopback-only PostgreSQL container, three generated
# databases and, in BrowserE2E mode, one loopback stack plus one browser
# container. It never accepts an inherited database URL, reads a repository
# .env, pulls an image, or invokes an older iteration runner.
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$productRoot = Join-Path $repoRoot "services\product_api"
$webRoot = Join-Path $repoRoot "services\web_ui"
$runId = [Guid]::NewGuid().ToString("N")
$short = $runId.Substring(0, 12)
$containerName = "iteration25-pg-$PID-$short"
$labelName = "com.b2b.iteration25.disposable"
$labelRun = "com.b2b.iteration25.run-id"
$labelRole = "com.b2b.iteration25.role"
$pgImage = "postgres:16.9-alpine@sha256:b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d"
$expectedPlaywrightImage = "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac"
$pgUser = "i24u$short"
$pgPassword = "i25p$runId"
$guardDatabase = "i24_guard_$short"
$roundtripDatabase = "i24_roundtrip_$short"
$suiteDatabase = "i25_suite_$short"
$expectedHead = "0019_company_card_v2_rollout_control"
$temporaryParent = Join-Path $repoRoot ".tmp"
$temporaryRoot = Join-Path $temporaryParent "iteration25-postgres-$runId"
$junit0018 = Join-Path $temporaryRoot "exact-0018.xml"
$junitAffected = Join-Path $temporaryRoot "affected-head.xml"
$junitBrowser = Join-Path $webRoot ".tmp\iteration25-playwright\junit.xml"
$browserManifest = Join-Path $temporaryRoot "company-card-v2-e2e-manifest.json"
$h2Extract = Join-Path $temporaryRoot "h2-release"
$runtimeExtract = Join-Path $temporaryRoot "playwright-runtime"
$claimsUpload = Join-Path $temporaryRoot "claims"
$containerId = $null
$productProcess = $null
$stackContainerId = $null
$browserContainerId = $null
$stackContainerName = "iteration25-stack-$PID-$short"
$browserContainerName = "iteration25-browser-$PID-$short"
$isWindowsHost = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [Runtime.InteropServices.OSPlatform]::Windows
)
$resolvedReleaseArtifactRoot = $null
$resolvedFontInventory = $null
$browserRuntimeMountPoint = [IO.Path]::GetFullPath((Join-Path $webRoot "node_modules"))
$ownsBrowserRuntimeMountPoint = $false
$primaryFailure = $null
$cleanupProblems = [Collections.Generic.List[string]]::new()
$junitDigests = @{}

$environmentNames = @(
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "TEST_POSTGRES_ADMIN_URL",
    "TEST_POSTGRES_GUARD_URL",
    "TEST_POSTGRES_ROUNDTRIP_URL",
    "TEST_NETWORK_GUARD_OWNER",
    "TEST_NETWORK_POSTGRES_URL",
    "COMPANY_CARD_V2_E2E_BASE_URL",
    "COMPANY_CARD_V2_E2E_MANIFEST",
    "SEO_PUBLIC_BASE_URL",
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_ADDOPTS",
    "APP_ENV",
    "LOG_LEVEL",
    "GATEWAY_URL",
    "GATEWAY_SHARED_SECRET",
    "AUTH_TOKEN_SECRET",
    "CLAIM_EDIT_TOKEN_SECRET",
    "INVITE_TOKEN_SECRET",
    "SESSION_SECRET",
    "PRODUCT_RELEASE_COMMIT",
    "OPENAI_API_KEY",
    "DATANEWTON_ENABLED",
    "DATANEWTON_BASE_URL",
    "DATANEWTON_API_KEY",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "CLAIMS_UPLOAD_DIR",
    "CLAIMS_PRICE_RUB",
    "CLAIMS_MAX_FILE_SIZE_BYTES",
    "CLAIMS_ALLOWED_UPLOAD_EXTENSIONS",
    "CLAIMS_ALLOWED_UPLOAD_MIME_TYPES",
    "CLAIMS_ADMIN_EMAILS",
    "CLAIMS_FIO_AI_ENABLED",
    "AI_EXPLANATION_ENABLED",
    "COMPANY_CARD_V2_PRESENTATIONS_ENABLED",
    "COMPANY_CARD_V2_WRITER_ENABLED",
    "COMPANY_CARD_V2_ROLLOUT_GENERATION",
    "COMPANY_CARD_V2_ALLOWLIST_INNS",
    "COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS",
    "COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED",
    "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID",
    "COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON",
    "COMPANY_CARD_AI_NARRATIVE_ENABLED",
    "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH",
    "COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED",
    "COMPANY_CARD_NARRATIVE_DAILY_CREDITS",
    "COMPANY_CARD_NARRATIVE_MONTHLY_CREDITS",
    "COMPANY_CARD_NARRATIVE_CONCURRENCY"
) | Select-Object -Unique

$savedEnvironment = @{}
foreach ($name in $environmentNames) {
    $savedEnvironment[$name] = [pscustomobject]@{
        Exists = Test-Path -LiteralPath "Env:\$name"
        Value = [Environment]::GetEnvironmentVariable($name, "Process")
    }
}

function Set-ProcessEnvironment {
    param([string]$Name, [AllowNull()][string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Assert-Exit {
    param([int]$Code, [string]$Operation)
    if ($Code -ne 0) {
        throw "$Operation failed with exit code $Code"
    }
}

function Assert-OwnedDatabaseName {
    param([string]$Database, [string]$ExpectedPrefix)
    if ($Database -notmatch "^$([regex]::Escape($ExpectedPrefix))[0-9a-f]{12}$") {
        throw "Refusing unknown PostgreSQL database target"
    }
}

function Get-OwnedContainerIdentity {
    param([string]$Id)
    $identity = ((& docker inspect --format '{{.Id}}|{{.Name}}' $Id) -join "").Trim()
    Assert-Exit $LASTEXITCODE "Container identity inspection"
    $labelsText = ((& docker inspect --format '{{json .Config.Labels}}' $Id) -join "").Trim()
    Assert-Exit $LASTEXITCODE "Container label inspection"
    try {
        $labels = $labelsText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "Docker returned malformed container labels"
    }
    return [pscustomobject]@{
        Identity = $identity
        Disposable = [string]$labels.PSObject.Properties[$labelName].Value
        Run = [string]$labels.PSObject.Properties[$labelRun].Value
        Role = [string]$labels.PSObject.Properties[$labelRole].Value
    }
}

function Assert-ExactOwnedContainer {
    param(
        [string]$Id,
        [string]$ExpectedName,
        [ValidateSet("postgres", "stack", "browser")]
        [string]$ExpectedRole
    )
    $actual = Get-OwnedContainerIdentity $Id
    if (
        $actual.Identity -ne "$Id|/$ExpectedName" -or
        $actual.Disposable -ne "true" -or
        $actual.Run -ne $runId -or
        $actual.Role -ne $ExpectedRole
    ) {
        throw "Container identity is outside this iteration-25 run"
    }
}

function Remove-ExactOwnedContainer {
    param(
        [AllowNull()][string]$Id,
        [string]$ExpectedName,
        [ValidateSet("postgres", "stack", "browser")]
        [string]$ExpectedRole
    )
    if ([string]::IsNullOrEmpty($Id)) {
        return
    }
    if ($Id -notmatch '^[a-f0-9]{64}$') {
        throw "Owned-container cleanup ID is malformed"
    }
    $matchingIds = @(
        & docker ps -aq --no-trunc --filter "id=$Id" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    Assert-Exit $LASTEXITCODE "Owned-container cleanup lookup"
    if (
        $matchingIds.Count -gt 1 -or
        ($matchingIds.Count -eq 1 -and $matchingIds[0] -ne $Id)
    ) {
        throw "Cleanup lookup did not resolve the captured container"
    }
    if ($matchingIds.Count -eq 1) {
        Assert-ExactOwnedContainer $Id $ExpectedName $ExpectedRole
        & docker rm --force --volumes $Id | Out-Null
        Assert-Exit $LASTEXITCODE "Owned-container cleanup"
    }
}

function Get-TimeNanoseconds {
    $value = ((& python -c "import time; print(time.time_ns())") -join "").Trim()
    Assert-Exit $LASTEXITCODE "Phase timestamp capture"
    if ($value -notmatch "^[0-9]+$") {
        throw "Python returned a malformed phase timestamp"
    }
    return $value
}

function Get-RunnerLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new(
        [Net.IPAddress]::Parse("127.0.0.1"),
        0
    )
    try {
        $listener.Start()
        $port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
        if ($port -lt 1 -or $port -gt 65535) {
            throw "Loopback port allocation returned an invalid port"
        }
        return $port
    }
    finally {
        $listener.Stop()
    }
}

function Start-OwnedApplication {
    param(
        [string]$FileName,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    $command = Get-Command $FileName -CommandType Application -ErrorAction Stop |
        Select-Object -First 1
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $command.Source
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    foreach ($argument in $ArgumentList) {
        $start.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::Start($start)
    if ($null -eq $process) {
        throw "Unable to start runner-owned application"
    }
    return $process
}

function Wait-LoopbackReady {
    param(
        [string]$Url,
        [AllowNull()][Diagnostics.Process]$Process,
        [AllowNull()][string]$DockerId,
        [string]$Label
    )
    if ($Url -notmatch '^http://127\.0\.0\.1:[1-9][0-9]{0,4}/[A-Za-z0-9_./-]+$') {
        throw "$Label readiness URL is not exact loopback HTTP"
    }
    if (($null -eq $Process) -eq [string]::IsNullOrEmpty($DockerId)) {
        throw "$Label readiness owner is ambiguous"
    }
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    try {
        for ($attempt = 0; $attempt -lt 120; $attempt++) {
            if ($null -ne $Process -and $Process.HasExited) {
                throw "$Label exited before readiness (exit $($Process.ExitCode))"
            }
            if (-not [string]::IsNullOrEmpty($DockerId)) {
                $state = ((& docker inspect --format '{{.State.Running}}|{{.State.ExitCode}}' $DockerId) -join "").Trim()
                Assert-Exit $LASTEXITCODE "$Label container state inspection"
                if ($state -notmatch '^true\|0$') {
                    throw "$Label container exited before readiness ($state)"
                }
            }
            try {
                $response = $client.GetAsync($Url).GetAwaiter().GetResult()
                try {
                    if ([int]$response.StatusCode -eq 200) {
                        return
                    }
                }
                finally {
                    $response.Dispose()
                }
            }
            catch [Net.Http.HttpRequestException] {
                # The owned process is still starting.
            }
            catch [Threading.Tasks.TaskCanceledException] {
                # The bounded readiness request timed out.
            }
            Start-Sleep -Milliseconds 250
        }
    }
    finally {
        $client.Dispose()
        $handler.Dispose()
    }
    throw "$Label did not become ready"
}

function Wait-ContainerLoopbackReady {
    param(
        [string]$Url,
        [string]$DockerId,
        [string]$Label
    )
    if ($Url -notmatch '^http://127\.0\.0\.1:[1-9][0-9]{0,4}/[A-Za-z0-9_./-]+$') {
        throw "$Label readiness URL is not exact loopback HTTP"
    }
    if ($DockerId -notmatch '^[a-f0-9]{64}$') {
        throw "$Label readiness owner is malformed"
    }
    $probe = 'fetch(process.argv[1],{redirect:"manual",signal:AbortSignal.timeout(2000)}).then(response=>process.exit(response.status===200?0:2),()=>process.exit(3))'
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        $state = ((& docker inspect --format '{{.State.Running}}|{{.State.ExitCode}}' $DockerId) -join "").Trim()
        Assert-Exit $LASTEXITCODE "$Label container state inspection"
        if ($state -notmatch '^true\|0$') {
            throw "$Label container exited before readiness ($state)"
        }
        & docker exec $DockerId node -e $probe $Url *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "$Label did not become ready"
}

function Stop-OwnedApplication {
    param(
        [AllowNull()][Diagnostics.Process]$Process,
        [string]$Label
    )
    if ($null -eq $Process) {
        return
    }
    try {
        if (-not $Process.HasExited) {
            $Process.Kill($true)
            if (-not $Process.WaitForExit(10000)) {
                throw "$Label did not terminate"
            }
        }
    }
    finally {
        $Process.Dispose()
    }
}

function Invoke-JUnitCheck {
    param([string]$Phase, [string]$Path, [string]$NotBeforeNanoseconds)
    & python (Join-Path $repoRoot "scripts\check-iteration25-test-results.py") `
        --phase $Phase `
        --junit $Path `
        --not-before-ns $NotBeforeNanoseconds
    Assert-Exit $LASTEXITCODE "$Phase JUnit validation"
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($digest -notmatch '^[0-9a-f]{64}$') {
        throw "$Phase JUnit digest is malformed"
    }
    $junitDigests[$Phase] = $digest
}

function Assert-DatabaseRevision {
    param([string]$Database, [string]$Revision)
    Assert-OwnedDatabaseName $Database $(if ($Database -eq $suiteDatabase) { "i25_suite_" } else { "i24_roundtrip_" })
    $actual = ((& docker exec $containerId psql --username $pgUser --dbname $Database --tuples-only --no-align --command "SELECT version_num FROM alembic_version") -join "").Trim()
    Assert-Exit $LASTEXITCODE "Alembic revision inspection"
    if ($actual -ne $Revision) {
        throw "Expected Alembic revision $Revision but observed $actual"
    }
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "AGENTS.md") -PathType Leaf)) {
        throw "Unable to resolve repository root"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $productRoot "alembic\versions\0019_company_card_v2_rollout_control.py") -PathType Leaf)) {
        throw "Required iteration-25 migration is missing"
    }
    $requiredCommands = @("docker", "python")
    if ($Mode -eq "BrowserE2E") {
        $requiredCommands += "git"
    }
    foreach ($command in $requiredCommands) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Required command is unavailable: $command"
        }
    }
    if ($Mode -eq "BrowserE2E") {
        if (
            [string]::IsNullOrEmpty($ReleaseArtifactRoot) -or
            [string]::IsNullOrEmpty($PlaywrightImage) -or
            [string]::IsNullOrEmpty($FontInventory) -or
            [string]::IsNullOrEmpty($ReleaseSha)
        ) {
            throw "BrowserE2E requires release artifacts, Playwright image, font inventory and release SHA"
        }
        if (
            -not [IO.Path]::IsPathFullyQualified($ReleaseArtifactRoot) -or
            -not [IO.Path]::IsPathFullyQualified($FontInventory)
        ) {
            throw "BrowserE2E artifact inputs must be absolute paths"
        }
        if ($PlaywrightImage -ne $expectedPlaywrightImage) {
            throw "BrowserE2E Playwright image differs from the frozen identity"
        }
        if ($ReleaseSha -notmatch '^[0-9a-f]{40}$') {
            throw "BrowserE2E release SHA must be exact lowercase 40-hex"
        }
        $rootItem = Get-Item -LiteralPath $ReleaseArtifactRoot -Force -ErrorAction Stop
        $fontItem = Get-Item -LiteralPath $FontInventory -Force -ErrorAction Stop
        if (
            -not $rootItem.PSIsContainer -or
            $fontItem.PSIsContainer -or
            ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            ($fontItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $null -ne $rootItem.LinkType -or
            $null -ne $fontItem.LinkType
        ) {
            throw "BrowserE2E artifacts must be plain directory/file inputs"
        }
        $resolvedReleaseArtifactRoot = $rootItem.FullName
        $resolvedFontInventory = $fontItem.FullName
        $trackedFontInventory = Join-Path $repoRoot ".github\ci\playwright-font-inventory.sha256"
        if (
            -not (Test-Path -LiteralPath $trackedFontInventory -PathType Leaf) -or
            (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedFontInventory).Hash -ne
            (Get-FileHash -Algorithm SHA256 -LiteralPath $trackedFontInventory).Hash -or
            (Get-Content -Raw -LiteralPath $resolvedFontInventory).Trim() -ne
            "705c330e71882ba9b680add251004054dcdc680b5c646e814b5b5ea2b6b341b3"
        ) {
            throw "BrowserE2E font inventory differs from the frozen identity"
        }
        $checkoutSha = ((& git -C $repoRoot rev-parse HEAD) -join "").Trim()
        Assert-Exit $LASTEXITCODE "BrowserE2E checkout SHA inspection"
        if ($checkoutSha -ne $ReleaseSha) {
            throw "BrowserE2E release SHA differs from checkout HEAD"
        }
        $h2Archive = Join-Path $resolvedReleaseArtifactRoot "company-public-h2-$ReleaseSha.tgz"
        $runtimeArchive = Join-Path $resolvedReleaseArtifactRoot "web-ui-playwright-runtime-$ReleaseSha.tgz"
        $releaseManifest = Join-Path $resolvedReleaseArtifactRoot "release-manifest-$ReleaseSha.json"
        $checksumFile = Join-Path $resolvedReleaseArtifactRoot "checksums-$ReleaseSha.txt"
        foreach ($artifact in @($h2Archive, $runtimeArchive, $releaseManifest, $checksumFile)) {
            $item = Get-Item -LiteralPath $artifact -Force -ErrorAction Stop
            if (
                $item.PSIsContainer -or
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                $null -ne $item.LinkType
            ) {
                throw "BrowserE2E release artifact is not a plain file"
            }
        }
        $checksums = @{}
        foreach ($line in Get-Content -LiteralPath $checksumFile) {
            if ($line -notmatch '^(?<hash>[0-9a-f]{64})  (?<name>[A-Za-z0-9][A-Za-z0-9._-]*)$') {
                throw "BrowserE2E checksum manifest is malformed"
            }
            if ($checksums.ContainsKey($Matches.name)) {
                throw "BrowserE2E checksum manifest contains a duplicate"
            }
            $checksums[$Matches.name] = $Matches.hash
        }
        foreach ($archive in @($h2Archive, $runtimeArchive)) {
            $name = Split-Path -Leaf $archive
            $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
            if (-not $checksums.ContainsKey($name) -or $checksums[$name] -ne $actualHash) {
                throw "BrowserE2E release artifact checksum mismatch"
            }
        }
        $releaseManifestGuard = Join-Path $repoRoot "deploy\product_api\release_manifest.py"
        $releaseManifestDigest = ((& python $releaseManifestGuard `
            $resolvedReleaseArtifactRoot `
            $ReleaseSha) -join "").Trim()
        Assert-Exit $LASTEXITCODE "BrowserE2E canonical release manifest validation"
        if ($releaseManifestDigest -notmatch '^[0-9a-f]{64}$') {
            throw "BrowserE2E release manifest validator returned a malformed digest"
        }
    }
    elseif (
        -not [string]::IsNullOrEmpty($ReleaseArtifactRoot) -or
        -not [string]::IsNullOrEmpty($PlaywrightImage) -or
        -not [string]::IsNullOrEmpty($FontInventory) -or
        -not [string]::IsNullOrEmpty($ReleaseSha) -or
        $UpdateSnapshots.IsPresent
    ) {
        throw "Artifact inputs are valid only in BrowserE2E mode"
    }
    foreach ($variable in @(
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "TEST_POSTGRES_ADMIN_URL",
        "TEST_POSTGRES_GUARD_URL",
        "TEST_POSTGRES_ROUNDTRIP_URL",
        "TEST_NETWORK_POSTGRES_URL"
    )) {
        if (Test-Path -LiteralPath "Env:\$variable") {
            throw "Refusing inherited database target: $variable"
        }
    }
    foreach ($environmentFile in @(
        (Join-Path $repoRoot ".env"),
        (Join-Path $productRoot ".env")
    )) {
        if (Test-Path -LiteralPath $environmentFile) {
            throw "Refusing repository environment file"
        }
    }
    foreach ($credential in @(
        "OPENAI_API_KEY",
        "DATANEWTON_API_KEY",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID",
        "COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"
    )) {
        if (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($credential, "Process"))) {
            throw "Unsafe inherited credential is set: $credential"
        }
    }
    $requiredSecrets = @{
        GATEWAY_SHARED_SECRET = "test-shared-secret"
        AUTH_TOKEN_SECRET = "test-auth-secret"
        CLAIM_EDIT_TOKEN_SECRET = "test-claim-edit-secret"
        INVITE_TOKEN_SECRET = "test-invite-secret"
        SESSION_SECRET = "test-session-secret"
    }
    foreach ($entry in $requiredSecrets.GetEnumerator()) {
        $current = [Environment]::GetEnvironmentVariable($entry.Key, "Process")
        if ($null -ne $current -and $current -ne $entry.Value) {
            throw "Unsafe inherited mandatory secret: $($entry.Key)"
        }
    }
    Assert-OwnedDatabaseName $guardDatabase "i24_guard_"
    Assert-OwnedDatabaseName $roundtripDatabase "i24_roundtrip_"
    Assert-OwnedDatabaseName $suiteDatabase "i25_suite_"
    if ($pgUser -ne "i24u$short") {
        throw "Frozen iteration-24 database owner shape is invalid"
    }

    & docker version --format '{{.Server.Version}}' | Out-Null
    Assert-Exit $LASTEXITCODE "Docker daemon preflight"
    & docker image inspect $pgImage --format '{{.Id}}' | Out-Null
    Assert-Exit $LASTEXITCODE "Local PostgreSQL image preflight"
    if ($Mode -eq "BrowserE2E") {
        & docker image inspect $PlaywrightImage --format '{{.Id}}' | Out-Null
        Assert-Exit $LASTEXITCODE "Local Playwright image preflight"
    }
    $existingOwned = @(
        & docker ps -aq --no-trunc --filter "label=$labelName=true" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    Assert-Exit $LASTEXITCODE "Iteration-25 owned-label preflight"
    if ($existingOwned.Count -ne 0) {
        throw "Refusing to adopt an existing iteration-25 container"
    }

    if (Test-Path -LiteralPath $temporaryParent) {
        $parentItem = Get-Item -LiteralPath $temporaryParent -Force
        if (($parentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Repository temporary parent must not be a reparse point"
        }
    }
    else {
        New-Item -ItemType Directory -Path $temporaryParent | Out-Null
    }
    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
    $temporaryItem = Get-Item -LiteralPath $temporaryRoot -Force
    if (($temporaryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Runner temporary directory must not be a reparse point"
    }
    if ($Mode -eq "BrowserE2E") {
        $archiveGuard = Join-Path $repoRoot "tests_support\archive_guard.py"
        $resolvedH2Root = ((& python $archiveGuard `
            --kind h2-release `
            --archive $h2Archive `
            --destination $h2Extract) -join "").Trim()
        Assert-Exit $LASTEXITCODE "H2 release archive extraction"
        $resolvedRuntimeRoot = ((& python $archiveGuard `
            --kind playwright-runtime `
            --archive $runtimeArchive `
            --destination $runtimeExtract) -join "").Trim()
        Assert-Exit $LASTEXITCODE "Playwright runtime archive extraction"
        $expectedH2Root = [IO.Path]::GetFullPath((Join-Path $h2Extract "company-public-h2"))
        $expectedRuntimeRoot = [IO.Path]::GetFullPath((Join-Path $runtimeExtract "node_modules"))
        if (
            $resolvedH2Root -ne $expectedH2Root -or
            $resolvedRuntimeRoot -ne $expectedRuntimeRoot -or
            -not (Test-Path -LiteralPath (Join-Path $resolvedRuntimeRoot "@playwright\test\package.json") -PathType Leaf)
        ) {
            throw "BrowserE2E extracted release graph is incomplete"
        }
        $resolvedAssetRoot = $resolvedH2Root
        $resolvedAssetManifest = Join-Path $resolvedH2Root "public_h2_asset_manifest.json"
        $packagedManifest = Join-Path $productRoot "src\product_api\company_reports\company_card_v2\public_h2_asset_manifest.json"
        if (
            -not (Test-Path -LiteralPath $resolvedAssetManifest -PathType Leaf) -or
            -not (Test-Path -LiteralPath $packagedManifest -PathType Leaf) -or
            (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedAssetManifest).Hash -ne
            (Get-FileHash -Algorithm SHA256 -LiteralPath $packagedManifest).Hash
        ) {
            throw "BrowserE2E release manifest differs from the packaged Product manifest"
        }
    }

    $dockerArguments = @(
        "run",
        "--detach",
        "--pull=never",
        "--platform", "linux/amd64",
        "--name", $containerName,
        "--label", "$labelName=true",
        "--label", "$labelRun=$runId",
        "--label", "$labelRole=postgres",
        "--publish", "127.0.0.1::5432",
        "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g",
        "--env", "POSTGRES_USER=$pgUser",
        "--env", "POSTGRES_PASSWORD=$pgPassword",
        "--env", "POSTGRES_DB=postgres",
        $pgImage
    )
    $containerId = ((& docker @dockerArguments) -join "").Trim()
    Assert-Exit $LASTEXITCODE "Disposable PostgreSQL startup"
    if ($containerId -notmatch "^[a-f0-9]{64}$") {
        throw "Docker did not return a full container ID"
    }
    Assert-ExactOwnedContainer $containerId $containerName "postgres"

    $portLine = ((& docker port $containerId "5432/tcp") -join "").Trim()
    Assert-Exit $LASTEXITCODE "PostgreSQL port lookup"
    if ($portLine -notmatch "^127\.0\.0\.1:(?<port>[1-9][0-9]{0,4})$") {
        throw "Disposable PostgreSQL is not loopback-only"
    }
    $port = [int]$Matches.port
    if ($port -gt 65535) {
        throw "Disposable PostgreSQL port is invalid"
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        & docker exec $containerId pg_isready --username $pgUser --dbname postgres *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        throw "Disposable PostgreSQL did not become ready"
    }
    foreach ($database in @($guardDatabase, $roundtripDatabase, $suiteDatabase)) {
        & docker exec $containerId createdb --username $pgUser --owner $pgUser $database
        Assert-Exit $LASTEXITCODE "Create runner-owned database"
    }

    $guardUrl = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${port}/${guardDatabase}"
    $roundtripUrl = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${port}/${roundtripDatabase}"
    $suiteUrl = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${port}/${suiteDatabase}"
    $adminUrl = "postgresql+asyncpg://${pgUser}:${pgPassword}@127.0.0.1:${port}/postgres"

    Set-ProcessEnvironment "PYTHONPATH" "$(Join-Path $productRoot 'src')$([IO.Path]::PathSeparator)$repoRoot"
    Set-ProcessEnvironment "PYTHONDONTWRITEBYTECODE" "1"
    Set-ProcessEnvironment "PYTEST_ADDOPTS" $null
    Set-ProcessEnvironment "APP_ENV" "dev"
    Set-ProcessEnvironment "LOG_LEVEL" "WARNING"
    Set-ProcessEnvironment "GATEWAY_URL" "http://127.0.0.1:9"
    foreach ($entry in $requiredSecrets.GetEnumerator()) {
        Set-ProcessEnvironment $entry.Key $entry.Value
    }
    Set-ProcessEnvironment "OPENAI_API_KEY" $null
    Set-ProcessEnvironment "DATANEWTON_ENABLED" "false"
    Set-ProcessEnvironment "DATANEWTON_BASE_URL" "http://127.0.0.1:9"
    Set-ProcessEnvironment "DATANEWTON_API_KEY" $null
    Set-ProcessEnvironment "SMTP_USER" $null
    Set-ProcessEnvironment "SMTP_PASSWORD" $null
    Set-ProcessEnvironment "EMAIL_FROM" "iteration25-tests@example.com"
    Set-ProcessEnvironment "CLAIMS_UPLOAD_DIR" $claimsUpload
    Set-ProcessEnvironment "CLAIMS_PRICE_RUB" "990"
    Set-ProcessEnvironment "CLAIMS_MAX_FILE_SIZE_BYTES" "10485760"
    Set-ProcessEnvironment "CLAIMS_ALLOWED_UPLOAD_EXTENSIONS" '[".pdf",".doc",".docx",".rtf",".jpg",".jpeg",".png"]'
    Set-ProcessEnvironment "CLAIMS_ALLOWED_UPLOAD_MIME_TYPES" '["application/pdf","application/msword","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/rtf","text/rtf","image/jpeg","image/png"]'
    Set-ProcessEnvironment "CLAIMS_ADMIN_EMAILS" '["claims-admin@example.com"]'
    Set-ProcessEnvironment "CLAIMS_FIO_AI_ENABLED" "false"
    Set-ProcessEnvironment "AI_EXPLANATION_ENABLED" "false"
    Set-ProcessEnvironment "COMPANY_CARD_V2_PRESENTATIONS_ENABLED" "false"
    Set-ProcessEnvironment "COMPANY_CARD_V2_WRITER_ENABLED" "false"
    Set-ProcessEnvironment "COMPANY_CARD_V2_ROLLOUT_GENERATION" "0"
    Set-ProcessEnvironment "COMPANY_CARD_V2_ALLOWLIST_INNS" ""
    Set-ProcessEnvironment "COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS" "0"
    Set-ProcessEnvironment "COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED" "false"
    Set-ProcessEnvironment "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID" $null
    Set-ProcessEnvironment "COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON" $null
    Set-ProcessEnvironment "COMPANY_CARD_AI_NARRATIVE_ENABLED" "false"
    Set-ProcessEnvironment "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH" "true"
    Set-ProcessEnvironment "COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED" "false"
    Set-ProcessEnvironment "COMPANY_CARD_NARRATIVE_DAILY_CREDITS" "0"
    Set-ProcessEnvironment "COMPANY_CARD_NARRATIVE_MONTHLY_CREDITS" "0"
    Set-ProcessEnvironment "COMPANY_CARD_NARRATIVE_CONCURRENCY" "0"
    Set-ProcessEnvironment "TEST_POSTGRES_ADMIN_URL" $adminUrl
    Set-ProcessEnvironment "TEST_POSTGRES_GUARD_URL" $guardUrl
    Set-ProcessEnvironment "TEST_POSTGRES_ROUNDTRIP_URL" $roundtripUrl
    Set-ProcessEnvironment "TEST_NETWORK_GUARD_OWNER" "iteration25"
    Set-ProcessEnvironment "PRODUCT_RELEASE_COMMIT" $(if ($Mode -eq "BrowserE2E") { $ReleaseSha } else { $null })
    Set-ProcessEnvironment "COMPANY_CARD_V2_E2E_BASE_URL" $null
    Set-ProcessEnvironment "COMPANY_CARD_V2_E2E_MANIFEST" $null
    Set-ProcessEnvironment "SEO_PUBLIC_BASE_URL" "http://127.0.0.1:9"

    $importPath = ((& python -c "import product_api; print(product_api.__file__)") -join "").Trim()
    Assert-Exit $LASTEXITCODE "Worktree import preflight"
    if (-not $importPath.StartsWith((Join-Path $productRoot "src"), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Python imported Product API outside the intended worktree"
    }

    if ($Mode -eq "PostgresFull") {
        Set-ProcessEnvironment "DATABASE_URL" $roundtripUrl
        Set-ProcessEnvironment "TEST_DATABASE_URL" $roundtripUrl
        Set-ProcessEnvironment "TEST_NETWORK_POSTGRES_URL" $roundtripUrl
        $phase0018Started = Get-TimeNanoseconds
        Push-Location $repoRoot
        try {
            & python -m pytest `
                services/product_api/tests/test_company_report_iteration24_migration.py `
                -q -ra -p no:cacheprovider "--junitxml=$junit0018"
            $phase0018Exit = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
        Assert-Exit $phase0018Exit "Exact-0018 compatibility phase"
        Invoke-JUnitCheck "exact-0018" $junit0018 $phase0018Started
        Assert-DatabaseRevision $roundtripDatabase "0018_company_card_v2_arbitration"

        Push-Location $productRoot
        try {
            & python -m alembic -c alembic.ini upgrade head
            Assert-Exit $LASTEXITCODE "Roundtrip 0018 to head upgrade"
        }
        finally {
            Pop-Location
        }
        Assert-DatabaseRevision $roundtripDatabase $expectedHead

        Set-ProcessEnvironment "DATABASE_URL" $suiteUrl
        Set-ProcessEnvironment "TEST_DATABASE_URL" $suiteUrl
        Set-ProcessEnvironment "TEST_NETWORK_POSTGRES_URL" $suiteUrl
        Push-Location $productRoot
        try {
            & python -m alembic -c alembic.ini upgrade head
            Assert-Exit $LASTEXITCODE "Affected-suite Alembic upgrade head"
        }
        finally {
            Pop-Location
        }
        Assert-DatabaseRevision $suiteDatabase $expectedHead

        $phaseAffectedStarted = Get-TimeNanoseconds
        Push-Location $repoRoot
        try {
            & python -m pytest `
                services/product_api/tests `
                --ignore=services/product_api/tests/test_company_report_iteration24_migration.py `
                -q -ra -p no:cacheprovider "--junitxml=$junitAffected"
            $phaseAffectedExit = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
        Assert-Exit $phaseAffectedExit "Affected-head PostgreSQL integration phase"
        Invoke-JUnitCheck "affected-head" $junitAffected $phaseAffectedStarted
    }
    else {
        Set-ProcessEnvironment "DATABASE_URL" $suiteUrl
        Set-ProcessEnvironment "TEST_DATABASE_URL" $suiteUrl
        Set-ProcessEnvironment "TEST_NETWORK_POSTGRES_URL" $suiteUrl
        Push-Location $productRoot
        try {
            & python -m alembic -c alembic.ini upgrade head
            Assert-Exit $LASTEXITCODE "BrowserE2E Alembic upgrade head"
        }
        finally {
            Pop-Location
        }
        Assert-DatabaseRevision $suiteDatabase $expectedHead

        & python (Join-Path $repoRoot "scripts\seed-iteration25-company-card-v2-acceptance.py") `
            --database-url $suiteUrl `
            --database-name $suiteDatabase `
            --release-sha $ReleaseSha `
            --manifest-output $browserManifest
        Assert-Exit $LASTEXITCODE "BrowserE2E acceptance seed"
        if (-not (Test-Path -LiteralPath $browserManifest -PathType Leaf)) {
            throw "BrowserE2E acceptance manifest is missing"
        }

        for ($portAttempt = 0; $portAttempt -lt 10; $portAttempt++) {
            $productPort = Get-RunnerLoopbackPort
            $publicPort = Get-RunnerLoopbackPort
            $productRelayPort = Get-RunnerLoopbackPort
            $allocatedPorts = @($productPort, $publicPort, $productRelayPort)
            if (@($allocatedPorts | Select-Object -Unique).Count -eq 3) {
                break
            }
        }
        if (@($allocatedPorts | Select-Object -Unique).Count -ne 3) {
            throw "Unable to allocate three distinct BrowserE2E loopback ports"
        }
        $productOrigin = "http://127.0.0.1:$productPort"
        $publicOrigin = "http://127.0.0.1:$publicPort"
        Set-ProcessEnvironment "SEO_PUBLIC_BASE_URL" $publicOrigin
        $productProcess = Start-OwnedApplication `
            -FileName "python" `
            -ArgumentList @(
                "-m", "uvicorn",
                "tests_support.network_guard:guarded_product_app",
                "--factory",
                "--host", "127.0.0.1",
                "--port", "$productPort"
            ) `
            -WorkingDirectory $repoRoot
        Wait-LoopbackReady `
            -Url "$productOrigin/health" `
            -Process $productProcess `
            -Label "BrowserE2E Product API"

        $productTargetHost = $(if ($isWindowsHost) { "host.docker.internal" } else { "127.0.0.1" })
        $stackArguments = [Collections.Generic.List[string]]::new()
        foreach ($argument in @(
            "run", "--detach", "--pull=never",
            "--platform", "linux/amd64"
        )) {
            $stackArguments.Add($argument)
        }
        if ($isWindowsHost) {
            $stackArguments.Add("--add-host")
            $stackArguments.Add("host.docker.internal:host-gateway")
        }
        else {
            $stackArguments.Add("--network")
            $stackArguments.Add("host")
        }
        foreach ($argument in @(
            "--name", $stackContainerName,
            "--label", "$labelName=true",
            "--label", "$labelRun=$runId",
            "--label", "$labelRole=stack",
            "--volume", "${repoRoot}:/workspace:ro",
            "--volume", "${resolvedAssetRoot}:/runner/h2:ro",
            "--workdir", "/workspace/services/web_ui",
            $PlaywrightImage,
            "node", "e2e/companyCardV2/loopback-stack.mjs",
            "--browser-port", "$publicPort",
            "--product-relay-port", "$productRelayPort",
            "--product-target-host", $productTargetHost,
            "--product-target-port", "$productPort",
            "--asset-root", "/runner/h2",
            "--asset-manifest", "/runner/h2/public_h2_asset_manifest.json"
        )) {
            $stackArguments.Add($argument)
        }
        $stackContainerId = ((& docker @stackArguments) -join "").Trim()
        Assert-Exit $LASTEXITCODE "BrowserE2E loopback stack startup"
        if ($stackContainerId -notmatch '^[a-f0-9]{64}$') {
            throw "Docker did not return the loopback stack container ID"
        }
        Assert-ExactOwnedContainer $stackContainerId $stackContainerName "stack"
        $stackNodeVersion = ((& docker exec $stackContainerId node --version) -join "").Trim()
        Assert-Exit $LASTEXITCODE "BrowserE2E loopback stack Node inspection"
        if ($stackNodeVersion -ne "v24.18.1") {
            throw "BrowserE2E loopback stack Node differs from the frozen identity"
        }
        Wait-ContainerLoopbackReady `
            -Url "http://127.0.0.1:$productRelayPort/health" `
            -DockerId $stackContainerId `
            -Label "BrowserE2E Product relay"
        Wait-ContainerLoopbackReady `
            -Url "$publicOrigin/__company-card-v2-e2e/ready" `
            -DockerId $stackContainerId `
            -Label "BrowserE2E same-origin stack"

        Set-ProcessEnvironment "COMPANY_CARD_V2_E2E_BASE_URL" $publicOrigin
        Set-ProcessEnvironment "COMPANY_CARD_V2_E2E_MANIFEST" $browserManifest
        $browserOutput = Join-Path $webRoot ".tmp\iteration25-playwright"
        if (-not (Test-Path -LiteralPath $browserOutput)) {
            New-Item -ItemType Directory -Path $browserOutput | Out-Null
        }
        $browserOutputItem = Get-Item -LiteralPath $browserOutput -Force
        if (
            -not $browserOutputItem.PSIsContainer -or
            ($browserOutputItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "BrowserE2E output must be a plain directory"
        }
        if (-not (Test-Path -LiteralPath $browserRuntimeMountPoint)) {
            New-Item -ItemType Directory -Path $browserRuntimeMountPoint | Out-Null
            $ownsBrowserRuntimeMountPoint = $true
        }
        $browserRuntimeMountPointItem = Get-Item `
            -LiteralPath $browserRuntimeMountPoint `
            -Force `
            -ErrorAction Stop
        if (
            [IO.Path]::GetFullPath($browserRuntimeMountPointItem.FullName) -ne $browserRuntimeMountPoint -or
            -not $browserRuntimeMountPointItem.PSIsContainer -or
            ($browserRuntimeMountPointItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $null -ne $browserRuntimeMountPointItem.LinkType
        ) {
            throw "BrowserE2E runtime mountpoint must be the exact plain node_modules directory"
        }
        if (
            $ownsBrowserRuntimeMountPoint -and
            @(Get-ChildItem -LiteralPath $browserRuntimeMountPoint -Force).Count -ne 0
        ) {
            throw "BrowserE2E runner-owned runtime mountpoint must remain empty"
        }
        $browserArguments = [Collections.Generic.List[string]]::new()
        foreach ($argument in @(
            "create", "--pull=never",
            "--platform", "linux/amd64",
            "--network", "container:$stackContainerId",
            "--ipc", "host",
            "--name", $browserContainerName,
            "--label", "$labelName=true",
            "--label", "$labelRun=$runId",
            "--label", "$labelRole=browser",
            "--volume", "${repoRoot}:/workspace:ro",
            "--volume", "${resolvedRuntimeRoot}:/workspace/services/web_ui/node_modules:ro",
            "--volume", "${browserManifest}:/runner/company-card-v2-e2e-manifest.json:ro",
            "--volume", "${browserOutput}:/workspace/services/web_ui/.tmp/iteration25-playwright:rw",
            "--env", "CI=1",
            "--env", "COMPANY_CARD_V2_E2E_BASE_URL=$publicOrigin",
            "--env", "COMPANY_CARD_V2_E2E_MANIFEST=/runner/company-card-v2-e2e-manifest.json",
            "--workdir", "/workspace"
        )) {
            $browserArguments.Add($argument)
        }
        if ($UpdateSnapshots.IsPresent) {
            $snapshotRoot = Join-Path $webRoot "e2e\companyCardV2\companyCardV2.spec.ts-snapshots"
            if (-not (Test-Path -LiteralPath $snapshotRoot)) {
                New-Item -ItemType Directory -Path $snapshotRoot | Out-Null
            }
            $snapshotItem = Get-Item -LiteralPath $snapshotRoot -Force
            if (
                -not $snapshotItem.PSIsContainer -or
                ($snapshotItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
            ) {
                throw "BrowserE2E snapshot target must be a plain directory"
            }
            $browserArguments.Add("--volume")
            $browserArguments.Add("${snapshotRoot}:/workspace/services/web_ui/e2e/companyCardV2/companyCardV2.spec.ts-snapshots:rw")
        }
        $browserArguments.Add($PlaywrightImage)
        foreach ($argument in @(
            "npm", "run",
            $(if ($UpdateSnapshots.IsPresent) { "test:e2e:update-snapshots" } else { "test:e2e:ci" }),
            "--prefix", "services/web_ui"
        )) {
            $browserArguments.Add($argument)
        }
        $phaseBrowserStarted = Get-TimeNanoseconds
        $browserContainerId = ((& docker @browserArguments) -join "").Trim()
        Assert-Exit $LASTEXITCODE "BrowserE2E Playwright container creation"
        if ($browserContainerId -notmatch '^[a-f0-9]{64}$') {
            throw "Docker did not return the browser container ID"
        }
        Assert-ExactOwnedContainer $browserContainerId $browserContainerName "browser"
        & docker start --attach $browserContainerId
        $phaseBrowserExit = $LASTEXITCODE
        Assert-Exit $phaseBrowserExit "BrowserE2E Playwright phase"
        Invoke-JUnitCheck "browser-e2e" $junitBrowser $phaseBrowserStarted
    }
}
catch {
    $primaryFailure = $_.Exception.Message.Replace($pgPassword, "<redacted>")
}
finally {
    foreach ($ownedContainer in @(
        [pscustomobject]@{ Id = $browserContainerId; Name = $browserContainerName; Role = "browser" },
        [pscustomobject]@{ Id = $stackContainerId; Name = $stackContainerName; Role = "stack" }
    )) {
        try {
            Remove-ExactOwnedContainer `
                -Id $ownedContainer.Id `
                -ExpectedName $ownedContainer.Name `
                -ExpectedRole $ownedContainer.Role
        }
        catch {
            $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
        }
    }
    if ($ownsBrowserRuntimeMountPoint) {
        try {
            if (Test-Path -LiteralPath $browserRuntimeMountPoint) {
                $browserRuntimeMountPointItem = Get-Item `
                    -LiteralPath $browserRuntimeMountPoint `
                    -Force `
                    -ErrorAction Stop
                if (
                    [IO.Path]::GetFullPath($browserRuntimeMountPointItem.FullName) -ne $browserRuntimeMountPoint -or
                    -not $browserRuntimeMountPointItem.PSIsContainer -or
                    ($browserRuntimeMountPointItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                    $null -ne $browserRuntimeMountPointItem.LinkType -or
                    @(Get-ChildItem -LiteralPath $browserRuntimeMountPoint -Force).Count -ne 0
                ) {
                    throw "BrowserE2E runtime mountpoint failed its exact empty ownership check"
                }
                Remove-Item -LiteralPath $browserRuntimeMountPoint -Force
            }
        }
        catch {
            $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
        }
    }
    try {
        Stop-OwnedApplication `
            -Process $productProcess `
            -Label "BrowserE2E Product API"
    }
    catch {
        $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
    }
    try {
        Remove-ExactOwnedContainer `
            -Id $containerId `
            -ExpectedName $containerName `
            -ExpectedRole "postgres"
    }
    catch {
        $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        try {
            $resolved = (Resolve-Path -LiteralPath $temporaryRoot).Path
            $expected = [IO.Path]::GetFullPath($temporaryRoot)
            $parentPrefix = [IO.Path]::GetFullPath($temporaryParent).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            $resolvedPrefix = $resolved.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            $item = Get-Item -LiteralPath $resolved -Force
            $reparseEntries = @(
                Get-ChildItem -LiteralPath $resolved -Force -Recurse |
                    Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 }
            )
            if (
                $resolved -ne $expected -or
                -not $resolved.StartsWith($parentPrefix, [StringComparison]::OrdinalIgnoreCase) -or
                (Split-Path -Leaf $resolved) -ne "iteration25-postgres-$runId" -or
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
            ) {
                throw "Temporary cleanup target failed its exact ownership check"
            }
            foreach ($entry in ($reparseEntries | Sort-Object { $_.FullName.Length } -Descending)) {
                $entryPath = [IO.Path]::GetFullPath($entry.FullName)
                if (-not $entryPath.StartsWith($resolvedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Temporary reparse cleanup target escaped runner ownership"
                }
                Remove-Item -LiteralPath $entryPath -Force
            }
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
        catch {
            $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
        }
    }
    foreach ($name in $environmentNames) {
        $saved = $savedEnvironment[$name]
        if ($saved.Exists) {
            Set-ProcessEnvironment $name ([string]$saved.Value)
        }
        else {
            Set-ProcessEnvironment $name $null
        }
    }
    try {
        $remainingOwned = @(
            & docker ps -aq --no-trunc --filter "label=$labelName=true" |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
        Assert-Exit $LASTEXITCODE "Iteration-25 owned-label cleanup proof"
        if ($remainingOwned.Count -ne 0) {
            throw "Iteration-25 owned-label namespace is not empty after cleanup"
        }
    }
    catch {
        $cleanupProblems.Add($_.Exception.Message.Replace($pgPassword, "<redacted>"))
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

if ($Mode -eq "BrowserE2E") {
    $browserDigest = [string]$junitDigests["browser-e2e"]
    if ($browserDigest -notmatch '^[0-9a-f]{64}$') {
        throw "BrowserE2E JUnit digest evidence is missing"
    }
    Write-Host "PASS iteration=25 phase=browser-e2e junit=clean junit_file=junit.xml junit_sha256=$browserDigest cleanup=confirmed"
}
else {
    $exact0018Digest = [string]$junitDigests["exact-0018"]
    $affectedHeadDigest = [string]$junitDigests["affected-head"]
    if (
        $exact0018Digest -notmatch '^[0-9a-f]{64}$' -or
        $affectedHeadDigest -notmatch '^[0-9a-f]{64}$'
    ) {
        throw "PostgreSQL JUnit digest evidence is missing"
    }
    Write-Host "PASS iteration=25 phases=exact-0018,affected-head junit=clean exact_0018_junit_file=exact-0018.xml exact_0018_junit_sha256=$exact0018Digest affected_head_junit_file=affected-head.xml affected_head_junit_sha256=$affectedHeadDigest cleanup=confirmed"
}
