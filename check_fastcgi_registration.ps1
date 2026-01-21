# Check FastCGI Registration
# Run as Administrator

Write-Host "Checking FastCGI Registration..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    exit 1
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

$pythonExe = "C:\Websites\NewHireApp\venv\Scripts\python.exe"
$wfastcgiPy = "C:\Websites\NewHireApp\venv\Lib\site-packages\wfastcgi.py"

Write-Host "1. Checking if Python and wfastcgi exist..." -ForegroundColor Yellow
if (Test-Path $pythonExe) {
    Write-Host "   Python: $pythonExe ✓" -ForegroundColor Green
} else {
    Write-Host "   Python: NOT FOUND ✗" -ForegroundColor Red
    exit 1
}

if (Test-Path $wfastcgiPy) {
    Write-Host "   wfastcgi.py: $wfastcgiPy ✓" -ForegroundColor Green
} else {
    Write-Host "   wfastcgi.py: NOT FOUND ✗" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "2. Checking FastCGI registration at server level..." -ForegroundColor Yellow
try {
    $fastCgiApps = Get-WebConfiguration -Filter "/system.webServer/fastCgi" -PSPath "IIS:\" -ErrorAction Stop
    $pythonApp = $fastCgiApps | Where-Object { $_.application.fullPath -eq $pythonExe }
    
    if ($pythonApp) {
        Write-Host "   FastCGI application registered: ✓" -ForegroundColor Green
        Write-Host "   Full Path: $($pythonApp.application.fullPath)" -ForegroundColor Gray
        Write-Host "   Arguments: $($pythonApp.application.arguments)" -ForegroundColor Gray
    } else {
        Write-Host "   FastCGI application NOT registered! ✗" -ForegroundColor Red
        Write-Host ""
        Write-Host "   SOLUTION: Run this to register:" -ForegroundColor Yellow
        Write-Host "   .\register_fastcgi.ps1" -ForegroundColor Cyan
        exit 1
    }
} catch {
    Write-Host "   Error checking FastCGI: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "3. Checking web.config handler..." -ForegroundColor Yellow
$webConfigPath = "C:\Websites\NewHireApp\web.config"
if (Test-Path $webConfigPath) {
    $config = [xml](Get-Content $webConfigPath)
    $handler = $config.configuration.'system.webServer'.handlers.add | Where-Object { $_.name -eq 'Python FastCGI' }
    
    if ($handler) {
        Write-Host "   Handler in web.config: ✓" -ForegroundColor Green
        $scriptProc = $handler.scriptProcessor
        Write-Host "   Script Processor: $scriptProc" -ForegroundColor Gray
        
        # Check if it matches registered FastCGI
        if ($scriptProc -eq "$pythonExe|$wfastcgiPy") {
            Write-Host "   ✓ Matches registered FastCGI application" -ForegroundColor Green
        } else {
            Write-Host "   ⚠ Does NOT match registered FastCGI!" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   Handler NOT found in web.config! ✗" -ForegroundColor Red
    }
} else {
    Write-Host "   web.config NOT found! ✗" -ForegroundColor Red
}

Write-Host ""
Write-Host "4. Testing if requests reach FastCGI..." -ForegroundColor Yellow
Write-Host "   Make a request to http://localhost:8080 and check the log:" -ForegroundColor Gray
Write-Host "   Get-Content C:\Websites\NewHireApp\logs\wfastcgi.log -Tail 10" -ForegroundColor Cyan

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If FastCGI is NOT registered, that's why you get 404." -ForegroundColor Yellow
Write-Host "IIS receives the request but can't process it." -ForegroundColor Yellow
Write-Host ""
Write-Host "Fix: Run .\register_fastcgi.ps1 as Administrator" -ForegroundColor Cyan
Write-Host ""
