# Quick Deployment Check Script
# Run this to verify your deployment is configured correctly

Write-Host "Checking Ziebart Onboarding App Deployment..." -ForegroundColor Cyan
Write-Host ""

$appPath = "C:\Websites\NewHireApp"
$siteName = "ZiebartOnboarding"
$appPoolName = "ZiebartOnboardingAppPool"

# Check if paths exist
Write-Host "1. Checking Application Path..." -ForegroundColor Yellow
if (Test-Path $appPath) {
    Write-Host "   ✓ Application path exists: $appPath" -ForegroundColor Green
} else {
    Write-Host "   ✗ Application path NOT found: $appPath" -ForegroundColor Red
}

# Check if web.config exists
Write-Host "2. Checking web.config..." -ForegroundColor Yellow
$webConfig = Join-Path $appPath "web.config"
if (Test-Path $webConfig) {
    Write-Host "   ✓ web.config found" -ForegroundColor Green
} else {
    Write-Host "   ✗ web.config NOT found" -ForegroundColor Red
}

# Check if venv exists
Write-Host "3. Checking Virtual Environment..." -ForegroundColor Yellow
$venvPath = Join-Path $appPath "venv"
if (Test-Path $venvPath) {
    Write-Host "   ✓ Virtual environment found" -ForegroundColor Green
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (Test-Path $pythonExe) {
        Write-Host "   ✓ Python executable found" -ForegroundColor Green
    } else {
        Write-Host "   ✗ Python executable NOT found" -ForegroundColor Red
    }
} else {
    Write-Host "   ✗ Virtual environment NOT found" -ForegroundColor Red
}

# Check if wfastcgi is installed
Write-Host "4. Checking wfastcgi..." -ForegroundColor Yellow
$wfastcgiPath = Join-Path $venvPath "Lib\site-packages\wfastcgi.py"
if (Test-Path $wfastcgiPath) {
    Write-Host "   ✓ wfastcgi.py found" -ForegroundColor Green
} else {
    Write-Host "   ✗ wfastcgi.py NOT found" -ForegroundColor Red
}

# Check IIS modules
Write-Host "5. Checking IIS Modules..." -ForegroundColor Yellow
Import-Module WebAdministration -ErrorAction SilentlyContinue
if (Get-Module WebAdministration) {
    Write-Host "   ✓ WebAdministration module loaded" -ForegroundColor Green
} else {
    Write-Host "   ✗ WebAdministration module NOT available" -ForegroundColor Red
}

# Check application pool
Write-Host "6. Checking Application Pool..." -ForegroundColor Yellow
if (Test-Path "IIS:\AppPools\$appPoolName") {
    $appPool = Get-Item "IIS:\AppPools\$appPoolName"
    Write-Host "   ✓ Application pool exists: $appPoolName" -ForegroundColor Green
    Write-Host "   State: $($appPool.state)" -ForegroundColor $(if ($appPool.state -eq "Started") { "Green" } else { "Yellow" })
} else {
    Write-Host "   ✗ Application pool NOT found: $appPoolName" -ForegroundColor Red
}

# Check website
Write-Host "7. Checking Website..." -ForegroundColor Yellow
if (Test-Path "IIS:\Sites\$siteName") {
    $site = Get-Item "IIS:\Sites\$siteName"
    Write-Host "   ✓ Website exists: $siteName" -ForegroundColor Green
    Write-Host "   State: $($site.state)" -ForegroundColor $(if ($site.state -eq "Started") { "Green" } else { "Yellow" })
    
    # Check bindings
    $bindings = Get-WebBinding -Name $siteName
    Write-Host "   Bindings:" -ForegroundColor Gray
    foreach ($binding in $bindings) {
        Write-Host "     - $($binding.protocol)://$($binding.bindingInformation)" -ForegroundColor Gray
    }
} else {
    Write-Host "   ✗ Website NOT found: $siteName" -ForegroundColor Red
}

# Check logs directory
Write-Host "8. Checking Logs Directory..." -ForegroundColor Yellow
$logsPath = Join-Path $appPath "logs"
if (Test-Path $logsPath) {
    Write-Host "   ✓ Logs directory exists" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Logs directory NOT found (will be created automatically)" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $logsPath -Force | Out-Null
    Write-Host "   ✓ Logs directory created" -ForegroundColor Green
}

# Check uploads directory
Write-Host "9. Checking Uploads Directory..." -ForegroundColor Yellow
$uploadsPath = Join-Path $appPath "uploads"
if (Test-Path $uploadsPath) {
    Write-Host "   ✓ Uploads directory exists" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Uploads directory NOT found (will be created automatically)" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $uploadsPath -Force | Out-Null
    Write-Host "   ✓ Uploads directory created" -ForegroundColor Green
}

Write-Host ""
Write-Host "Deployment Check Complete!" -ForegroundColor Cyan
Write-Host ""
