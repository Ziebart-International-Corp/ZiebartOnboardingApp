# Install Windows Authentication Feature for IIS
# Run as Administrator
# Works on both Windows Server and Windows 10/11

Write-Host "Installing Windows Authentication for IIS..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Detect Windows version
$isServer = (Get-CimInstance Win32_OperatingSystem).ProductType -eq 3

Write-Host "Detected Windows: $(if ($isServer) { 'Server' } else { 'Client' })" -ForegroundColor Gray
Write-Host ""

Write-Host "Step 1: Installing Windows Authentication feature..." -ForegroundColor Yellow

if ($isServer) {
    # Windows Server - use Install-WindowsFeature
    Write-Host "  Using Server Manager cmdlets..." -ForegroundColor Gray
    try {
        $feature = Get-WindowsFeature -Name IIS-WindowsAuthentication -ErrorAction SilentlyContinue
        if ($feature -and $feature.InstallState -eq "Installed") {
            Write-Host "  Windows Authentication is already installed" -ForegroundColor Green
        } else {
            Write-Host "  Installing Windows Authentication..." -ForegroundColor Gray
            $result = Install-WindowsFeature -Name IIS-WindowsAuthentication
            if ($result.Success) {
                Write-Host "  Windows Authentication installed successfully!" -ForegroundColor Green
            } else {
                Write-Host "  ERROR: Failed to install Windows Authentication" -ForegroundColor Red
                exit 1
            }
        }
    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Trying alternative feature names..." -ForegroundColor Yellow
        
        # Try alternative names
        $featureNames = @("IIS-WindowsAuthentication", "IIS-ASPNET45", "IIS-Security")
        foreach ($name in $featureNames) {
            try {
                Write-Host "  Trying: $name" -ForegroundColor Gray
                Install-WindowsFeature -Name $name -ErrorAction Stop | Out-Null
                Write-Host "  Installed: $name" -ForegroundColor Green
            } catch {
                # Continue to next
            }
        }
    }
} else {
    # Windows 10/11 Client - use Enable-WindowsOptionalFeature
    Write-Host "  Using Optional Features cmdlets..." -ForegroundColor Gray
    try {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName IIS-ASPNET45 -ErrorAction SilentlyContinue
        if ($feature -and $feature.State -eq "Enabled") {
            Write-Host "  Windows Authentication components are already installed" -ForegroundColor Green
        } else {
            Write-Host "  Installing IIS Windows Authentication..." -ForegroundColor Gray
            
            # Enable the feature using DISM
            $result = Enable-WindowsOptionalFeature -Online -FeatureName IIS-ASPNET45 -All -NoRestart -ErrorAction Stop
            if ($result.RestartNeeded) {
                Write-Host "  Windows Authentication installed! Restart may be required." -ForegroundColor Green
            } else {
                Write-Host "  Windows Authentication installed successfully!" -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "  Trying DISM command directly..." -ForegroundColor Yellow
        try {
            $dismResult = DISM /Online /Enable-Feature /FeatureName:IIS-ASPNET45 /All /NoRestart
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  Windows Authentication installed via DISM!" -ForegroundColor Green
            } else {
                Write-Host "  ERROR: DISM command failed" -ForegroundColor Red
                Write-Host "  Exit code: $LASTEXITCODE" -ForegroundColor Red
            }
        } catch {
            Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host ""
            Write-Host "  Manual Installation Required:" -ForegroundColor Yellow
            Write-Host "  1. Open 'Turn Windows features on or off'" -ForegroundColor White
            Write-Host "  2. Navigate to: Internet Information Services > World Wide Web Services > Security" -ForegroundColor White
            Write-Host "  3. Check 'Windows Authentication'" -ForegroundColor White
            Write-Host "  4. Click OK" -ForegroundColor White
            exit 1
        }
    }
}

Write-Host ""
Write-Host "Step 2: Verifying installation..." -ForegroundColor Yellow

# Check if Windows Authentication module is available
$authModule = Get-Module -ListAvailable -Name WebAdministration -ErrorAction SilentlyContinue
if ($authModule) {
    Import-Module WebAdministration -ErrorAction SilentlyContinue
    Write-Host "  WebAdministration module loaded" -ForegroundColor Green
} else {
    Write-Host "  WARNING: WebAdministration module not found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 3: Restarting IIS..." -ForegroundColor Yellow
try {
    iisreset /restart
    Write-Host "  IIS restarted successfully" -ForegroundColor Green
} catch {
    Write-Host "  Could not restart IIS automatically" -ForegroundColor Yellow
    Write-Host "  Please restart IIS manually: iisreset" -ForegroundColor Yellow
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
Write-Host "If Windows Authentication still doesn't appear, install it manually:" -ForegroundColor Yellow
Write-Host "  - Open 'Turn Windows features on or off' (optionalfeatures)" -ForegroundColor White
Write-Host "  - Internet Information Services > World Wide Web Services > Security" -ForegroundColor White
Write-Host "  - Check 'Windows Authentication'" -ForegroundColor White
Write-Host ""
