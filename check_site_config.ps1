# Check ZiebartOnboarding Site Configuration
# Run as Administrator

Write-Host "Checking ZiebartOnboarding Site Configuration..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    exit 1
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

$siteName = "ZiebartOnboarding"

if (-not (Test-Path "IIS:\Sites\$siteName")) {
    Write-Host "ERROR: Site '$siteName' does not exist!" -ForegroundColor Red
    exit 1
}

Write-Host "1. Site Status:" -ForegroundColor Yellow
$site = Get-Website -Name $siteName
Write-Host "   State: $($site.State)" -ForegroundColor $(if ($site.State -eq 'Started') { 'Green' } else { 'Red' })
Write-Host "   Physical Path: $($site.physicalPath)" -ForegroundColor Gray

Write-Host ""
Write-Host "2. Bindings:" -ForegroundColor Yellow
$bindings = Get-WebBinding -Name $siteName
foreach ($binding in $bindings) {
    Write-Host "   $($binding.protocol) : $($binding.bindingInformation)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "3. Application Pool:" -ForegroundColor Yellow
$appPoolName = (Get-Item "IIS:\Sites\$siteName").applicationPool
Write-Host "   Name: $appPoolName" -ForegroundColor Cyan
$appPool = Get-Item "IIS:\AppPools\$appPoolName"
Write-Host "   State: $($appPool.State)" -ForegroundColor $(if ($appPool.State -eq 'Started') { 'Green' } else { 'Red' })

Write-Host ""
Write-Host "4. Testing localhost access..." -ForegroundColor Yellow
$port = 8080
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$port" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   localhost:$port - Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   localhost:$port - Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "   Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "5. Checking web.config..." -ForegroundColor Yellow
$webConfigPath = Join-Path $site.physicalPath "web.config"
if (Test-Path $webConfigPath) {
    Write-Host "   web.config exists: ✓" -ForegroundColor Green
    $config = [xml](Get-Content $webConfigPath)
    
    # Check for FastCGI handler
    $handler = $config.configuration.'system.webServer'.handlers.add | Where-Object { $_.name -eq 'Python FastCGI' }
    if ($handler) {
        Write-Host "   FastCGI handler found: ✓" -ForegroundColor Green
        Write-Host "   Script Processor: $($handler.scriptProcessor)" -ForegroundColor Gray
    } else {
        Write-Host "   FastCGI handler NOT found!" -ForegroundColor Red
    }
    
    # Check for URL Rewrite
    $rewrite = $config.configuration.'system.webServer'.rewrite
    if ($rewrite) {
        Write-Host "   URL Rewrite rules found: ✓" -ForegroundColor Green
    } else {
        Write-Host "   URL Rewrite rules NOT found!" -ForegroundColor Red
    }
} else {
    Write-Host "   web.config NOT found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Diagnosis:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If you're accessing ziebartonboarding.com (no port), but the site" -ForegroundColor Yellow
Write-Host "is configured on port 8080, you need to either:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  A. Access: http://ziebartonboarding.com:8080" -ForegroundColor Cyan
Write-Host "  B. Add a binding on port 80" -ForegroundColor Cyan
Write-Host ""
