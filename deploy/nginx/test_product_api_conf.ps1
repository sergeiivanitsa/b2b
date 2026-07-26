$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw (Join-Path $PSScriptRoot 'product_api.conf')
foreach ($needle in @('auth_request /internal/whoami;', 'error_page 401 = @company_public_ssr;', 'location @company_public_ssr', 'location = /robots.txt', 'location = /sitemaps/index.xml')) {
  if (-not $config.Contains($needle)) { throw "Missing nginx SEO contract: $needle" }
}
if ($config -notmatch 'location ~ \^/company/\(\?:\[0-9\]\{10\}\|\[0-9\]\{12\}\)') { throw 'Company route must require exactly 10 or 12 INN digits' }
if ($config -notmatch 'location @company_public_ssr \{[\s\S]*proxy_pass http://127\.0\.0\.1:8000;') { throw 'Named SSR location must use proxy_pass without URI part' }
if ($config -match '(?i)user-agent.*company|company.*user-agent') { throw 'Company routing must not branch on User-Agent' }
Write-Output 'nginx product API SEO routing contract passed'
