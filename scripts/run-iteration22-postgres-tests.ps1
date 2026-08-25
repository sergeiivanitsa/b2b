[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateSet('Targeted','Full')][string]$Mode)

# Independent, disposable PostgreSQL runner for iteration 22.  It never calls
# an earlier iteration runner and validates its own fresh JUnit result.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$productRoot = Join-Path $repoRoot 'services\product_api'
$run = [guid]::NewGuid().ToString('N'); $short = $run.Substring(0,12)
$name = "iteration22-pg-$PID-$short"; $label = 'com.b2b.iteration22.disposable'; $runLabel = 'com.b2b.iteration22.run-id'
$junitDir = Join-Path $repoRoot '.tmp\iteration22-postgres'
$junitName = if ($Mode -eq 'Targeted') { 'targeted.xml' } else { 'full.xml' }
$junit = Join-Path $junitDir $junitName
$id = $null; $saved = @{}
function Env([string]$key, [AllowNull()][string]$value) { [Environment]::SetEnvironmentVariable($key,$value,'Process') }
function Check([string]$label) { if($LASTEXITCODE -ne 0){ throw "$label failed: $LASTEXITCODE" } }
$names = @('DATABASE_URL','TEST_DATABASE_URL','TEST_POSTGRES_ADMIN_URL','PYTHONPATH','APP_ENV','GATEWAY_URL','GATEWAY_SHARED_SECRET','AUTH_TOKEN_SECRET','CLAIM_EDIT_TOKEN_SECRET','INVITE_TOKEN_SECRET','SESSION_SECRET','EMAIL_FROM','CLAIMS_PRICE_RUB','CLAIMS_UPLOAD_DIR','OPENAI_API_KEY','DATANEWTON_ENABLED','AI_EXPLANATION_ENABLED','CLAIMS_FIO_AI_ENABLED','COMPANY_CARD_V2_WRITER_ENABLED','COMPANY_CARD_V2_PRESENTATIONS_ENABLED','COMPANY_CARD_V2_ROLLOUT_GENERATION','COMPANY_CARD_V2_ALLOWLIST_INNS','COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS','COMPANY_CARD_AI_NARRATIVE_ENABLED','COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH','COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED')
try {
  foreach($envFile in @((Join-Path $repoRoot '.env'),(Join-Path $productRoot '.env'))){if(Test-Path -LiteralPath $envFile){throw "Refusing unreviewed .env: $envFile"}}
  foreach($n in $names){$saved[$n]=[Environment]::GetEnvironmentVariable($n,'Process')}
  & docker version --format '{{.Server.Version}}' | Out-Null; Check 'Docker preflight'
  & docker image inspect postgres:16-alpine --format '{{.Id}}' | Out-Null; Check 'postgres image preflight'
  New-Item -ItemType Directory -Force -Path $junitDir | Out-Null; if(Test-Path -LiteralPath $junit){Remove-Item -Force -LiteralPath $junit}
  $user="i22u$short"; $pass="i22p$run"; $db="i22d$short"
  $id=(( & docker run --detach --pull=never --name $name --label "$label=true" --label "$runLabel=$run" --publish '127.0.0.1::5432' --tmpfs '/var/lib/postgresql/data:rw,noexec,nosuid,size=1g' --env "POSTGRES_USER=$user" --env "POSTGRES_PASSWORD=$pass" --env "POSTGRES_DB=$db" postgres:16-alpine)-join '').Trim(); Check 'postgres start'
  $mapping=(( & docker port $id '5432/tcp')-join '').Trim(); Check 'port lookup'; if($mapping -notmatch '^127\.0\.0\.1:(?<port>[1-9][0-9]{0,4})$'){throw 'PostgreSQL must use dynamic loopback port'}
  $ready=$false; for($i=0;$i -lt 60;$i++){& docker exec $id pg_isready -U $user -d $db *> $null;if($LASTEXITCODE -eq 0){$ready=$true;break};Start-Sleep -Seconds 1};if(!$ready){throw 'PostgreSQL readiness failed'}
  $url="postgresql+asyncpg://${user}:${pass}@127.0.0.1:$($Matches.port)/$db"; Env DATABASE_URL $url;Env TEST_DATABASE_URL $url;Env TEST_POSTGRES_ADMIN_URL "postgresql+asyncpg://${user}:${pass}@127.0.0.1:$($Matches.port)/postgres";Env PYTHONPATH "$productRoot\src$([IO.Path]::PathSeparator)$repoRoot";Env APP_ENV 'dev';Env GATEWAY_URL 'http://127.0.0.1:9';Env GATEWAY_SHARED_SECRET 'iteration22-gateway';Env AUTH_TOKEN_SECRET 'iteration22-auth';Env CLAIM_EDIT_TOKEN_SECRET 'iteration22-claim';Env INVITE_TOKEN_SECRET 'iteration22-invite';Env SESSION_SECRET 'iteration22-session';Env EMAIL_FROM 'iteration22@example.test';Env CLAIMS_PRICE_RUB '990';Env CLAIMS_UPLOAD_DIR (Join-Path ([IO.Path]::GetTempPath()) "iteration22-claims-$run")
  foreach($n in $names | Where-Object {$_ -match 'OPENAI|DATANEWTON|AI_EXPLANATION|CLAIMS_FIO|COMPANY_CARD'}){Env $n $null}; Env DATANEWTON_ENABLED 'false';Env AI_EXPLANATION_ENABLED 'false';Env CLAIMS_FIO_AI_ENABLED 'false';Env COMPANY_CARD_V2_WRITER_ENABLED 'false';Env COMPANY_CARD_V2_PRESENTATIONS_ENABLED 'false';Env COMPANY_CARD_V2_ROLLOUT_GENERATION '0';Env COMPANY_CARD_V2_ALLOWLIST_INNS '';Env COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS '0';Env COMPANY_CARD_AI_NARRATIVE_ENABLED 'false';Env COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH 'true';Env COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED 'false'
  $import=(( & python -c 'import product_api; print(product_api.__file__)')-join '').Trim();if(!$import.StartsWith((Join-Path $productRoot 'src'),[StringComparison]::OrdinalIgnoreCase)){throw "Python import outside current worktree: $import"}
  Push-Location $productRoot;try{& python -m alembic -c alembic.ini upgrade head;Check 'Alembic upgrade'}finally{Pop-Location}
  $targets=if($Mode -eq 'Targeted'){@('services/product_api/tests/test_company_report_public_h1_reads.py','services/product_api/tests/test_company_report_public_h2_reads.py','services/product_api/tests/test_company_report_public_documents.py','services/product_api/tests/test_company_report_presentations.py','services/product_api/tests/test_claims_company_report_handoff.py')}else{@('services/product_api/tests')};foreach($target in $targets){if(!(Test-Path -LiteralPath (Join-Path $repoRoot $target))){throw "Missing required target: $target"}}
  Push-Location $repoRoot;try{& python -m pytest $targets -q -ra -p no:cacheprovider "--junitxml=$junit";Check "$Mode PostgreSQL tests"}finally{Pop-Location}
  [xml]$xml=Get-Content -Raw -LiteralPath $junit;$cases=@($xml.SelectNodes('//testcase'));$bad=@($xml.SelectNodes('//failure|//error|//skipped'));if($cases.Count -eq 0 -or $bad.Count -ne 0){throw 'JUnit evidence is not clean'};Write-Host "PASS mode=$Mode tests=$($cases.Count) junit=$junit"
} finally {if($id){$labels=(( & docker inspect --format '{{json .Config.Labels}}' $id)-join '')|ConvertFrom-Json;if($labels.$label -eq 'true' -and $labels.$runLabel -eq $run){& docker rm --force --volumes $id|Out-Null}};foreach($n in $saved.Keys){Env $n $saved[$n]}}
