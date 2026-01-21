# Fix Windows Authentication Configuration
# Run this script if authentication configuration failed during deployment

Write-Host "Fixing Windows Authentication Configuration..." -ForegroundColor Cyan
Write-Host ""

$siteName = "ZiebartOnboarding"

# Check if site exists
if (-not (Test-Path "IIS:\Sites\$siteName")) {
    Write-Host "ERROR: Site '$siteName' not found!" -ForegroundColor Red
    exit 1
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

Write-Host "Current Authentication Settings:" -ForegroundColor Yellow
$winAuth = Get-WebConfigurationProperty -Filter "system.webServer/security/authentication/windowsAuthentication" -Name enabled -PSPath "IIS:\Sites\$siteName" -ErrorAction SilentlyContinue
$anonAuth = Get-WebConfigurationProperty -Filter "system.webServer/security/authentication/anonymousAuthentication" -Name enabled -PSPath "IIS:\Sites\$siteName" -ErrorAction SilentlyContinue

Write-Host "  Windows Authentication: $($winAuth.Value)" -ForegroundColor $(if ($winAuth.Value) { "Green" } else { "Red" })
Write-Host "  Anonymous Authentication: $($anonAuth.Value)" -ForegroundColor $(if (-not $anonAuth.Value) { "Green" } else { "Red" })

Write-Host ""
Write-Host "Attempting to configure authentication..." -ForegroundColor Yellow

# Method 1: Try using Set-WebConfigurationProperty with explicit path
try {
    $config = Get-WebConfiguration -Filter "system.webServer/security/authentication/windowsAuthentication" -PSPath "IIS:\Sites\$siteName"
    $config.enabled = $true
    Set-WebConfiguration -Filter "system.webServer/security/authentication/windowsAuthentication" -PSPath "IIS:\Sites\$siteName" -Value @{enabled="True"}
    Write-Host "  ✓ Windows Authentication enabled" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to enable Windows Authentication via Set-WebConfiguration" -ForegroundColor Red
    Write-Host "    Error: $($_.Exception.Message)" -ForegroundColor Red
}

try {
    Set-WebConfiguration -Filter "system.webServer/security/authentication/anonymousAuthentication" -PSPath "IIS:\Sites\$siteName" -Value @{enabled="False"}
    Write-Host "  ✓ Anonymous Authentication disabled" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to disable Anonymous Authentication" -ForegroundColor Red
    Write-Host "    Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "If the above methods failed, please configure manually:" -ForegroundColor Yellow
Write-Host "1. Open IIS Manager" -ForegroundColor White
Write-Host "2. Navigate to Sites > $siteName" -ForegroundColor White
Write-Host "3. Double-click 'Authentication'" -ForegroundColor White
Write-Host "4. Right-click 'Windows Authentication' > Enable" -ForegroundColor White
Write-Host "5. Right-click 'Anonymous Authentication' > Disable" -ForegroundColor White
Write-Host ""

# Verify final state
Write-Host "Final Authentication Settings:" -ForegroundColor Yellow
$winAuth = Get-WebConfigurationProperty -Filter "system.webServer/security/authentication/windowsAuthentication" -Name enabled -PSPath "IIS:\Sites\$siteName" -ErrorAction SilentlyContinue
$anonAuth = Get-WebConfigurationProperty -Filter "system.webServer/security/authentication/anonymousAuthentication" -Name enabled -PSPath "IIS:\Sites\$siteName" -ErrorAction SilentlyContinue

if ($winAuth -and $winAuth.Value -and $anonAuth -and -not $anonAuth.Value) {
    Write-Host "  Authentication configured correctly!" -ForegroundColor Green
} else {
    Write-Host "  Authentication may need manual configuration" -ForegroundColor Yellow
}
