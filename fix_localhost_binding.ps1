# Fix Localhost Binding for ZiebartOnboarding Site
# Adds localhost binding so you can test locally
# Run as Administrator

Write-Host "Fixing Localhost Binding for ZiebartOnboarding..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

$siteName = "ZiebartOnboarding"
$port = 8080

# Check if site exists
if (-not (Test-Path "IIS:\Sites\$siteName")) {
    Write-Host "ERROR: Site '$siteName' does not exist!" -ForegroundColor Red
    exit 1
}

Write-Host "1. Checking current bindings..." -ForegroundColor Yellow
$currentBindings = Get-WebBinding -Name $siteName
Write-Host "   Current bindings:" -ForegroundColor Gray
foreach ($binding in $currentBindings) {
    Write-Host "     $($binding.protocol) : $($binding.bindingInformation)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "2. Checking for localhost/catch-all binding..." -ForegroundColor Yellow
$hasLocalhost = $false
$hasCatchAll = $false

foreach ($binding in $currentBindings) {
    $info = $binding.bindingInformation
    if ($info -match "localhost" -or $info -match "127.0.0.1") {
        $hasLocalhost = $true
        Write-Host "   ✓ Localhost binding found: $info" -ForegroundColor Green
    }
    if ($info -match "^\*:$port$" -or $info -match "^\*:$port:") {
        $hasCatchAll = $true
        Write-Host "   ✓ Catch-all binding found: $info" -ForegroundColor Green
    }
}

Write-Host ""
if (-not $hasLocalhost -and -not $hasCatchAll) {
    Write-Host "3. Adding catch-all binding for localhost access..." -ForegroundColor Yellow
    try {
        # Add catch-all binding (no hostname) on port 8080
        New-WebBinding -Name $siteName -Protocol http -IPAddress "*" -Port $port -ErrorAction Stop
        Write-Host "   ✓ Catch-all binding added: *:$port" -ForegroundColor Green
    } catch {
        Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "   Trying alternative method..." -ForegroundColor Yellow
        
        # Alternative: Add explicit localhost binding
        try {
            New-WebBinding -Name $siteName -Protocol http -HostHeader "localhost" -Port $port -ErrorAction Stop
            Write-Host "   ✓ Localhost binding added: *:$port:localhost" -ForegroundColor Green
        } catch {
            Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
} else {
    Write-Host "3. Localhost/catch-all binding already exists." -ForegroundColor Green
}

Write-Host ""
Write-Host "4. Verifying final bindings..." -ForegroundColor Yellow
$finalBindings = Get-WebBinding -Name $siteName
Write-Host "   Final bindings:" -ForegroundColor Gray
foreach ($binding in $finalBindings) {
    $info = $binding.bindingInformation
    Write-Host "     $($binding.protocol) : $info" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "5. Restarting site..." -ForegroundColor Yellow
Stop-Website -Name $siteName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-Website -Name $siteName -ErrorAction SilentlyContinue
Write-Host "   Site restarted." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Binding Fix Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "You can now access:" -ForegroundColor Yellow
Write-Host "  http://localhost:8080" -ForegroundColor Cyan
Write-Host "  http://ziebartonboarding.com:8080" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: IIS will route based on hostname:" -ForegroundColor Gray
Write-Host "  - localhost:8080 → catch-all binding" -ForegroundColor Gray
Write-Host "  - ziebartonboarding.com:8080 → hostname binding" -ForegroundColor Gray
Write-Host ""
