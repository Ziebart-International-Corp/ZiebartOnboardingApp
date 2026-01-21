# Add Port 80 Binding for ZiebartOnboarding Site
# This allows access without specifying port number
# Run as Administrator

Write-Host "Adding Port 80 Binding for ZiebartOnboarding..." -ForegroundColor Cyan
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
$hostname = "ziebartonboarding.com"
$port = 80

# Check if site exists
if (-not (Test-Path "IIS:\Sites\$siteName")) {
    Write-Host "ERROR: Site '$siteName' does not exist!" -ForegroundColor Red
    exit 1
}

Write-Host "1. Checking for existing port 80 binding..." -ForegroundColor Yellow
$portPattern = ":$port:"
$existingBindings = Get-WebBinding -Name $siteName | Where-Object { $_.bindingInformation -match $portPattern }
if ($existingBindings) {
    Write-Host "   Port 80 bindings found:" -ForegroundColor Yellow
    foreach ($binding in $existingBindings) {
        Write-Host "     $($binding.bindingInformation)" -ForegroundColor Gray
        if ($binding.bindingInformation -match $hostname) {
            Write-Host "   [OK] Hostname binding on port 80 already exists!" -ForegroundColor Green
            exit 0
        }
    }
}

Write-Host ""
Write-Host "2. Adding port 80 binding with hostname..." -ForegroundColor Yellow
try {
    New-WebBinding -Name $siteName -Protocol http -HostHeader $hostname -Port $port -ErrorAction Stop
    $bindingInfo = "*:${port}:${hostname}"
    Write-Host "   [OK] Port 80 binding added: $bindingInfo" -ForegroundColor Green
} catch {
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    
    # Check if port 80 is already in use by another site
    $portPattern = ":$port:"
    $port80Sites = Get-Website | Where-Object {
        $bindings = Get-WebBinding -Name $_.Name
        $bindings | Where-Object { $_.bindingInformation -match $portPattern }
    }
    
    if ($port80Sites) {
        Write-Host ""
        Write-Host "   WARNING: Port 80 is already in use by:" -ForegroundColor Yellow
        foreach ($site in $port80Sites) {
            Write-Host "     - $($site.Name)" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "   You can still use port 8080: http://ziebartonboarding.com:8080" -ForegroundColor Cyan
    }
    exit 1
}

Write-Host ""
Write-Host "3. Verifying bindings..." -ForegroundColor Yellow
$allBindings = Get-WebBinding -Name $siteName
Write-Host "   Current bindings:" -ForegroundColor Gray
foreach ($binding in $allBindings) {
    Write-Host "     $($binding.protocol) : $($binding.bindingInformation)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "4. Restarting site..." -ForegroundColor Yellow
Stop-Website -Name $siteName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-Website -Name $siteName -ErrorAction SilentlyContinue
Write-Host "   Site restarted." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Port 80 Binding Added!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "You can now access:" -ForegroundColor Yellow
Write-Host "  http://ziebartonboarding.com" -ForegroundColor Cyan
Write-Host "  http://ziebartonboarding.com:8080" -ForegroundColor Cyan
Write-Host ""
