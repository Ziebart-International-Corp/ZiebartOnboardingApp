# Install Windows Authentication Feature for IIS
# Run as Administrator

Write-Host "Installing Windows Authentication for IIS..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "Step 1: Installing Windows Authentication feature..." -ForegroundColor Yellow
$feature = Get-WindowsFeature -Name IIS-WindowsAuthentication -ErrorAction SilentlyContinue

if ($feature -and $feature.InstallState -eq "Installed") {
    Write-Host "  Windows Authentication is already installed" -ForegroundColor Green
} else {
    Write-Host "  Installing Windows Authentication..." -ForegroundColor Gray
    $result = Install-WindowsFeature -Name IIS-WindowsAuthentication
    
    if ($result.Success) {
        Write-Host "  Windows Authentication installed successfully!" -ForegroundColor Green
        Write-Host "  You may need to restart IIS or the server for changes to take effect." -ForegroundColor Yellow
    } else {
        Write-Host "  ERROR: Failed to install Windows Authentication" -ForegroundColor Red
        Write-Host "  Exit code: $($result.ExitCode)" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Step 2: Verifying installation..." -ForegroundColor Yellow
$feature = Get-WindowsFeature -Name IIS-WindowsAuthentication
if ($feature.InstallState -eq "Installed") {
    Write-Host "  Windows Authentication is installed" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Windows Authentication may not be fully installed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 3: Restarting IIS..." -ForegroundColor Yellow
try {
    iisreset /restart
    Write-Host "  IIS restarted successfully" -ForegroundColor Green
} catch {
    Write-Host "  Could not restart IIS automatically" -ForegroundColor Yellow
    Write-Host "  Please restart IIS manually or restart the server" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Close and reopen IIS Manager" -ForegroundColor White
Write-Host "2. Navigate to: Sites > ZiebartOnboarding > Authentication" -ForegroundColor White
Write-Host "3. You should now see 'Windows Authentication' in the list" -ForegroundColor White
Write-Host "4. Enable 'Windows Authentication'" -ForegroundColor White
Write-Host "5. Disable 'Anonymous Authentication'" -ForegroundColor White
Write-Host ""
