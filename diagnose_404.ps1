# Diagnose 404 Error for ziebartonboarding.com
# Run as Administrator

Write-Host "Diagnosing 404 Error..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    exit 1
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

$siteName = "ZiebartOnboarding"
$hostname = "ziebartonboarding.com"

Write-Host "1. Checking site status..." -ForegroundColor Yellow
if (-not (Test-Path "IIS:\Sites\$siteName")) {
    Write-Host "   ERROR: Site '$siteName' does not exist!" -ForegroundColor Red
    exit 1
}

$site = Get-Website -Name $siteName
Write-Host "   State: $($site.State)" -ForegroundColor $(if ($site.State -eq 'Started') { 'Green' } else { 'Red' })
Write-Host "   Physical Path: $($site.physicalPath)" -ForegroundColor Gray

Write-Host ""
Write-Host "2. Checking bindings..." -ForegroundColor Yellow
$bindings = Get-WebBinding -Name $siteName
$hasPort80 = $false
$hasHostname = $false

foreach ($binding in $bindings) {
    $info = $binding.bindingInformation
    Write-Host "   $($binding.protocol) : $info" -ForegroundColor Cyan
    
    if ($info -match ":80:" -or $info -match ":80$") {
        $hasPort80 = $true
        if ($info -match $hostname) {
            $hasHostname = $true
            Write-Host "     ✓ Port 80 with hostname found!" -ForegroundColor Green
        }
    }
}

if (-not $hasPort80) {
    Write-Host ""
    Write-Host "   WARNING: No port 80 binding found!" -ForegroundColor Red
    Write-Host "   You're accessing ziebartonboarding.com (port 80)" -ForegroundColor Yellow
    Write-Host "   but the site might only be on port 8080." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "3. Checking web.config..." -ForegroundColor Yellow
$webConfigPath = Join-Path $site.physicalPath "web.config"
if (Test-Path $webConfigPath) {
    Write-Host "   web.config exists: ✓" -ForegroundColor Green
    
    $config = [xml](Get-Content $webConfigPath)
    
    # Check FastCGI handler
    $handler = $config.configuration.'system.webServer'.handlers.add | Where-Object { $_.name -eq 'Python FastCGI' }
    if ($handler) {
        Write-Host "   FastCGI handler: ✓" -ForegroundColor Green
        $scriptProc = $handler.scriptProcessor
        if (Test-Path ($scriptProc -split '\|')[0]) {
            Write-Host "   Python executable exists: ✓" -ForegroundColor Green
        } else {
            Write-Host "   Python executable NOT found: $($scriptProc -split '\|')[0]" -ForegroundColor Red
        }
    } else {
        Write-Host "   FastCGI handler: ✗ NOT FOUND!" -ForegroundColor Red
    }
    
    # Check URL Rewrite
    $rewrite = $config.configuration.'system.webServer'.rewrite
    if ($rewrite) {
        Write-Host "   URL Rewrite rules: ✓" -ForegroundColor Green
    } else {
        Write-Host "   URL Rewrite rules: ✗ NOT FOUND!" -ForegroundColor Red
    }
} else {
    Write-Host "   web.config NOT found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "4. Checking FastCGI registration..." -ForegroundColor Yellow
$fastCgiConfig = Get-WebConfiguration -Filter "/system.webServer/fastCgi/application" -PSPath "IIS:\" -ErrorAction SilentlyContinue
if ($fastCgiConfig) {
    Write-Host "   FastCGI applications registered: ✓" -ForegroundColor Green
    foreach ($app in $fastCgiConfig) {
        if ($app.fullPath -match "python.exe") {
            Write-Host "     Python FastCGI: $($app.fullPath)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "   FastCGI NOT registered at server level!" -ForegroundColor Red
    Write-Host "   Run: .\register_fastcgi.ps1" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "5. Checking wfastcgi log..." -ForegroundColor Yellow
$logPath = "C:\Websites\NewHireApp\logs\wfastcgi.log"
if (Test-Path $logPath) {
    $logContent = Get-Content $logPath -Tail 10 -ErrorAction SilentlyContinue
    if ($logContent) {
        Write-Host "   Recent log entries:" -ForegroundColor Gray
        $logContent | ForEach-Object { Write-Host "     $_" -ForegroundColor Gray }
    } else {
        Write-Host "   Log file is empty or no recent entries" -ForegroundColor Yellow
    }
} else {
    Write-Host "   Log file not found: $logPath" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "6. Testing localhost access..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   localhost:8080 - Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   localhost:8080 - Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "   Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Diagnosis Summary:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not $hasPort80) {
    Write-Host "ISSUE: No port 80 binding found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Solution: Add port 80 binding:" -ForegroundColor Yellow
    Write-Host "  Run: .\add_port80_binding.ps1" -ForegroundColor Cyan
    Write-Host "  Or access: http://ziebartonboarding.com:8080" -ForegroundColor Cyan
} else {
    Write-Host "Port 80 binding exists. Checking other issues..." -ForegroundColor Yellow
    
    if (-not $handler) {
        Write-Host "ISSUE: FastCGI handler not configured in web.config!" -ForegroundColor Red
    }
    
    if (-not $rewrite) {
        Write-Host "ISSUE: URL Rewrite rules not configured!" -ForegroundColor Red
    }
}

Write-Host ""
