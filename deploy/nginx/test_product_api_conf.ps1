$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw (Join-Path $PSScriptRoot 'product_api.conf')
foreach ($needle in @('proxy_intercept_errors on;', 'error_page 404 = @company_spa;', 'location @company_spa', 'location = /robots.txt', 'location = /sitemaps/index.xml')) {
  if (-not $config.Contains($needle)) { throw "Missing nginx SEO contract: $needle" }
}
if ($config -notmatch 'location ~ "\^/company/\(\?:\[0-9\]\{10\}\|\[0-9\]\{12\}\)') { throw 'Company route must require exactly 10 or 12 INN digits' }
if ($config -notmatch 'location ~ "\^/company/[\s\S]*proxy_pass http://127\.0\.0\.1:8000;[\s\S]*error_page 404 = @company_spa;') { throw 'Canonical CompanyReport route must use SSR with a 404-only SPA fallback' }
if ($config -notmatch 'location @company_spa \{[\s\S]*try_files \$uri \$uri/ /index\.html;') { throw 'CompanyReport SPA fallback must serve index.html' }
if ($config -match 'error_page (?:401|403|429|5[0-9]{2}) = @company_spa;') { throw 'CompanyReport SPA fallback must not cloak non-404 errors' }
if ($config -match '(?i)user-agent.*company|company.*user-agent') { throw 'Company routing must not branch on User-Agent' }
Write-Output 'nginx product API SEO routing contract passed'
