$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw (Join-Path $PSScriptRoot 'product_api.conf')
$publicConfig = Get-Content -Raw (Join-Path $PSScriptRoot 'pork.su.conf')
foreach ($needle in @('proxy_intercept_errors on;', 'error_page 404 = @company_h1_spa;', 'location @company_h1_spa', 'location ^~ /assets/company-public-h2.', 'root /var/lib/pork/company-public-h2/v1;', 'root /var/lib/pork/web-ui/v1/current/site;', 'try_files $uri =404;', 'location = /robots.txt', 'location = /sitemaps/index.xml')) {
  if (-not $config.Contains($needle)) { throw "Missing product nginx SEO contract: $needle" }
  if ($needle -in @('location ^~ /assets/company-public-h2.', 'root /var/lib/pork/company-public-h2/v1;', 'try_files $uri =404;') -and -not $publicConfig.Contains($needle)) { throw "Missing public nginx H2 contract: $needle" }
}
if ($config.Contains('root /opt/b2b/services/web_ui/dist;') -or $publicConfig.Contains('root /opt/b2b/services/web_ui/dist;')) { throw 'SPA must use the atomic SHA-bound release pointer' }
if ($config -match 'location \^~ /assets/company-public-h2\. \{[\s\S]*?alias ') { throw 'H2 immutable assets must preserve the URI with root, not alias' }
if ($config -notmatch 'location ~ "\^/company/\(\?:\[0-9\]\{10\}\|\[0-9\]\{12\}\)') { throw 'Company route must require exactly 10 or 12 INN digits' }
if ($config -notmatch 'location ~ "\^/company/\(\?:\[0-9\]\{10\}\|\[0-9\]\{12\}\)\$"[\s\S]*error_page 404 = @company_h1_spa;') { throw 'Plain INN route must use the only 404 SPA fallback' }
if ($config -match 'location ~ "\^/company/[\s\S]*\)-\[a-z0-9\][\s\S]*error_page') { throw 'Canonical CompanyReport route must not fall back to SPA' }
if ($publicConfig -match 'location \^~ /assets/company-public-h2\. \{[\s\S]*?alias ') { throw 'Public H2 immutable assets must preserve URI with root, not alias' }
if ($config -notmatch 'location @company_h1_spa \{[\s\S]*try_files \$uri \$uri/ /index\.html;') { throw 'CompanyReport SPA fallback must serve index.html' }
if ($config -match 'error_page (?:401|403|429|5[0-9]{2}) = @company_h1_spa;') { throw 'CompanyReport SPA fallback must not cloak non-404 errors' }
if ($config -match '(?i)user-agent.*company|company.*user-agent') { throw 'Company routing must not branch on User-Agent' }
Write-Output 'nginx product API SEO routing contract passed'
