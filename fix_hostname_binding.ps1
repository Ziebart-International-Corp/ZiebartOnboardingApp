# Fix Hostname Binding for ZiebartOnboarding Site
# This ensures ziebartonboarding.com routes to the correct site
# Run as Administrator

Write-Host "Fixing Hostname Binding for ZiebartOnboarding..." -ForegroundColor Cyan
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
Write-Host "2. Removing existing bindings without hostname..." -ForegroundColor Yellow
# Remove bindings that don't have the hostname (to avoid conflicts)
foreach ($binding in $currentBindings) {
    $info = $binding.bindingInformation
    # If it's port 8080 but doesn't have the hostname, remove it
    if ($info -match ":$port" -and $info -notmatch $hostname) {
        Write-Host "   Removing: $($binding.protocol) : $info" -ForegroundColor Gray
        Remove-WebBinding -Name $siteName -Protocol $binding.protocol -BindingInformation $info -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "3. Adding/Updating hostname binding..." -ForegroundColor Yellow
# Check if hostname binding already exists
$hostBinding = Get-WebBinding -Name $siteName | Where-Object { $_.bindingInformation -match $hostname }
if ($hostBinding) {
    Write-Host "   Hostname binding already exists: $($hostBinding.bindingInformation)" -ForegroundColor Green
} else {
    # Add hostname binding
    $bindingInfo = "*:${port}:$hostname"
    try {
        New-WebBinding -Name $siteName -Protocol http -HostHeader $hostname -Port $port -ErrorAction Stop
        Write-Host "   ✓ Hostname binding added: $bindingInfo" -ForegroundColor Green
    } catch {
        Write-Host "   Binding might already exist, checking..." -ForegroundColor Yellow
        # Try to add with explicit binding information
        try {
            New-WebBinding -Name $siteName -Protocol http -BindingInformation $bindingInfo -ErrorAction Stop
            Write-Host "   ✓ Hostname binding added: $bindingInfo" -ForegroundColor Green
        } catch {
            Write-Host "   Note: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "4. Verifying final bindings..." -ForegroundColor Yellow
$finalBindings = Get-WebBinding -Name $siteName
Write-Host "   Final bindings:" -ForegroundColor Gray
foreach ($binding in $finalBindings) {
    $info = $binding.bindingInformation
    if ($info -match $hostname) {
        Write-Host "     $($binding.protocol) : $info ✓" -ForegroundColor Green
    } else {
        Write-Host "     $($binding.protocol) : $info" -ForegroundColor Gray
    }
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
Write-Host "The site should now respond to:" -ForegroundColor Yellow
Write-Host "  http://ziebartonboarding.com:8080" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: Make sure DNS resolves ziebartonboarding.com to this server's IP." -ForegroundColor Yellow
Write-Host "      If accessing from another computer, configure DNS or hosts file." -ForegroundColor Yellow
