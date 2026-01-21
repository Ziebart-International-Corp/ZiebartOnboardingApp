# Check IIS Bindings for All Sites
# Run as Administrator

Write-Host "Checking IIS Site Bindings..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

Write-Host "All IIS Sites and Their Bindings:" -ForegroundColor Yellow
Write-Host "=================================" -ForegroundColor Yellow
Write-Host ""

$sites = Get-Website
foreach ($site in $sites) {
    Write-Host "Site: $($site.Name)" -ForegroundColor Green
    Write-Host "  State: $($site.State)" -ForegroundColor Gray
    $bindings = Get-WebBinding -Name $site.Name
    foreach ($binding in $bindings) {
        $info = $binding.bindingInformation
        $protocol = $binding.protocol
        Write-Host "    $protocol : $info" -ForegroundColor Cyan
    }
    Write-Host ""
}

Write-Host "Checking for conflicts..." -ForegroundColor Yellow
Write-Host ""

# Check if ziebartonboarding.com binding exists
$targetSite = "ZiebartOnboarding"
$targetHost = "ziebartonboarding.com"
$targetPort = 8080

$targetBindings = Get-WebBinding -Name $targetSite -ErrorAction SilentlyContinue
$hasHostBinding = $false

Write-Host "Bindings for $targetSite:" -ForegroundColor Yellow
foreach ($binding in $targetBindings) {
    $info = $binding.bindingInformation
    Write-Host "  $($binding.protocol) : $info" -ForegroundColor Cyan
    
    # Check if hostname binding exists
    if ($info -match $targetHost) {
        $hasHostBinding = $true
        Write-Host "    ✓ Hostname binding found!" -ForegroundColor Green
    }
}

if (-not $hasHostBinding) {
    Write-Host ""
    Write-Host "WARNING: No hostname binding found for $targetHost" -ForegroundColor Red
    Write-Host "This means requests might go to the default site or another site." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Checking for port 8080 conflicts..." -ForegroundColor Yellow
$port8080Sites = $sites | Where-Object {
    $bindings = Get-WebBinding -Name $_.Name
    $bindings | Where-Object { $_.bindingInformation -match ":8080" }
}

if ($port8080Sites.Count -gt 1) {
    Write-Host "WARNING: Multiple sites using port 8080:" -ForegroundColor Red
    foreach ($site in $port8080Sites) {
        Write-Host "  - $($site.Name)" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "IIS will route based on hostname. Make sure hostname bindings are unique." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Checking default site..." -ForegroundColor Yellow
$defaultSite = Get-Website -Name "Default Web Site" -ErrorAction SilentlyContinue
if ($defaultSite) {
    $defaultBindings = Get-WebBinding -Name "Default Web Site"
    Write-Host "Default Web Site bindings:" -ForegroundColor Yellow
    foreach ($binding in $defaultBindings) {
        Write-Host "  $($binding.protocol) : $($binding.bindingInformation)" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "If Default Web Site has a catch-all binding, it might intercept requests." -ForegroundColor Yellow
}
