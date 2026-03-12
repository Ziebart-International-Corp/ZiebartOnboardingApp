# IIS Deployment Script for Ziebart Onboarding App
# Run this script as Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Ziebart Onboarding App - IIS Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Application paths
$appPath = "C:\Websites\NewHireApp"
$siteName = "ZiebartOnboarding"
$appPoolName = "ZiebartOnboardingAppPool"
$hostname = "ziebartonboarding.com"
# Port configuration - Change this if port 8080 is also in use
$port = 8082  # Avoid conflicts (80, 8080, 8081, etc. in use)

# Check if port is already in use
Write-Host "Checking if port $port is available..." -ForegroundColor Yellow
$portInUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "  WARNING: Port $port is already in use!" -ForegroundColor Red
    Write-Host "  Please specify a different port or stop the service using this port." -ForegroundColor Yellow
    Write-Host "  You can change the port by editing this script (line 10: `$port = XXXX)" -ForegroundColor Yellow
    Write-Host "  Or run deploy_iis_custom_port.ps1 for interactive port selection" -ForegroundColor Yellow
    $continue = Read-Host "  Continue anyway? (y/n)"
    if ($continue -ne "y") {
        exit 1
    }
} else {
    Write-Host "  Port $port is available" -ForegroundColor Green
}
Write-Host ""

# Check if app path exists
if (-not (Test-Path $appPath)) {
    Write-Host "ERROR: Application path not found: $appPath" -ForegroundColor Red
    exit 1
}

Write-Host "Step 1: Installing IIS Features..." -ForegroundColor Yellow
Import-Module ServerManager -ErrorAction SilentlyContinue
$features = @(
    "IIS-WebServerRole",
    "IIS-WebServer",
    "IIS-CommonHttpFeatures",
    "IIS-HttpErrors",
    "IIS-ApplicationInit",
    "IIS-NetFxExtensibility45",
    "IIS-HealthAndDiagnostics",
    "IIS-HttpLogging",
    "IIS-Security",
    "IIS-RequestFiltering",
    "IIS-Performance",
    "IIS-HttpCompressionStatic",
    "IIS-WebServerManagementTools",
    "IIS-ManagementConsole",
    "IIS-IIS6ManagementCompatibility",
    "IIS-Metabase",
    "IIS-WindowsAuthentication"
)

foreach ($feature in $features) {
    $installed = Get-WindowsFeature -Name $feature -ErrorAction SilentlyContinue
    if ($installed -and $installed.InstallState -ne "Installed") {
        Write-Host "  Installing $feature..." -ForegroundColor Gray
        Install-WindowsFeature -Name $feature -ErrorAction SilentlyContinue | Out-Null
    }
}

Write-Host "Step 2: Importing WebAdministration module..." -ForegroundColor Yellow
Import-Module WebAdministration -ErrorAction SilentlyContinue

Write-Host "Step 3: Creating Application Pool..." -ForegroundColor Yellow
# Remove existing app pool if it exists
if (Test-Path "IIS:\AppPools\$appPoolName") {
    Write-Host "  Removing existing application pool..." -ForegroundColor Gray
    Remove-WebAppPool -Name $appPoolName -ErrorAction SilentlyContinue
}

# Create new app pool
New-WebAppPool -Name $appPoolName -Force | Out-Null
$appPool = Get-Item "IIS:\AppPools\$appPoolName"
$appPool.managedRuntimeVersion = ""
$appPool.managedPipelineMode = "Integrated"
$appPool.processModel.identityType = "ApplicationPoolIdentity"
$appPool.startMode = "AlwaysRunning"
$appPool | Set-Item

Write-Host "  Application pool created: $appPoolName" -ForegroundColor Green

Write-Host "Step 4: Creating IIS Site..." -ForegroundColor Yellow
# Remove existing site if it exists
if (Test-Path "IIS:\Sites\$siteName") {
    Write-Host "  Removing existing site..." -ForegroundColor Gray
    Remove-Website -Name $siteName -ErrorAction SilentlyContinue
}

# Create new site
New-Website -Name $siteName -Port $port -PhysicalPath $appPath -ApplicationPool $appPoolName -Force | Out-Null

# Add hostname binding (port in $port and port 80 for clean URL)
New-WebBinding -Name $siteName -Protocol http -HostHeader $hostname -Port $port -ErrorAction SilentlyContinue
New-WebBinding -Name $siteName -Protocol http -HostHeader $hostname -Port 80 -ErrorAction SilentlyContinue

Write-Host "  Site created: $siteName" -ForegroundColor Green
Write-Host "  Bindings: http://$hostname and http://$hostname`:$port" -ForegroundColor Green

Write-Host "Step 5: Setting up permissions..." -ForegroundColor Yellow
# Grant permissions to application pool identity
$appPoolIdentity = "IIS AppPool\$appPoolName"
$acl = Get-Acl $appPath
$accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule($appPoolIdentity, "ReadAndExecute", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.SetAccessRule($accessRule)
Set-Acl -Path $appPath -AclObject $acl

# Grant write permissions to logs and uploads directories
$logsPath = Join-Path $appPath "logs"
$uploadsPath = Join-Path $appPath "uploads"
if (Test-Path $logsPath) {
    $logsAcl = Get-Acl $logsPath
    $logsAcl.SetAccessRule($accessRule)
    Set-Acl -Path $logsPath -AclObject $logsAcl
}
if (Test-Path $uploadsPath) {
    $uploadsAcl = Get-Acl $uploadsPath
    $uploadsAcl.SetAccessRule($accessRule)
    Set-Acl -Path $uploadsPath -AclObject $uploadsAcl
}

Write-Host "  Permissions configured" -ForegroundColor Green

Write-Host "Step 6: Configuring Windows Authentication..." -ForegroundColor Yellow
try {
    # Enable Windows Authentication at site level
    Set-WebConfigurationProperty -Filter "system.webServer/security/authentication/windowsAuthentication" -Name enabled -Value $true -PSPath "IIS:\Sites\$siteName" -ErrorAction Stop
    Write-Host "  Windows Authentication enabled" -ForegroundColor Green
} catch {
    Write-Host "  Warning: Could not enable Windows Authentication via PowerShell" -ForegroundColor Yellow
    Write-Host "  You may need to enable it manually in IIS Manager:" -ForegroundColor Yellow
    Write-Host "    - Select the site '$siteName'" -ForegroundColor Yellow
    Write-Host "    - Double-click 'Authentication'" -ForegroundColor Yellow
    Write-Host "    - Enable 'Windows Authentication'" -ForegroundColor Yellow
    Write-Host "    - Disable 'Anonymous Authentication'" -ForegroundColor Yellow
}

try {
    # Disable Anonymous Authentication
    Set-WebConfigurationProperty -Filter "system.webServer/security/authentication/anonymousAuthentication" -Name enabled -Value $false -PSPath "IIS:\Sites\$siteName" -ErrorAction Stop
    Write-Host "  Anonymous Authentication disabled" -ForegroundColor Green
} catch {
    Write-Host "  Warning: Could not disable Anonymous Authentication via PowerShell" -ForegroundColor Yellow
}

Write-Host "Step 7: Starting Application Pool..." -ForegroundColor Yellow
try {
    Start-WebAppPool -Name $appPoolName -ErrorAction Stop
    Write-Host "  Application pool started" -ForegroundColor Green
} catch {
    Write-Host "  Application pool may already be running" -ForegroundColor Yellow
}

try {
    $site = Get-Website -Name $siteName -ErrorAction Stop
    if ($site.State -ne "Started") {
        Start-Website -Name $siteName -ErrorAction Stop
        Write-Host "  Website started" -ForegroundColor Green
    } else {
        Write-Host "  Website is already running" -ForegroundColor Green
    }
} catch {
    Write-Host "  Warning: Could not start website. It may already be running or there may be a binding conflict." -ForegroundColor Yellow
    Write-Host "  Check IIS Manager to verify the site status." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Site Name: $siteName" -ForegroundColor Cyan
Write-Host "URL: http://$hostname`:$port" -ForegroundColor Cyan
Write-Host "Application Pool: $appPoolName" -ForegroundColor Cyan
Write-Host "Physical Path: $appPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Configure DNS to point $hostname to this server's IP address" -ForegroundColor White
Write-Host "2. Access the application at: http://$hostname`:$port" -ForegroundColor White
Write-Host "   (Note: Using port $port instead of default port 80)" -ForegroundColor Yellow
Write-Host "3. If using HTTPS, add SSL certificate binding on port 443" -ForegroundColor White
Write-Host "4. Check logs at: $appPath\logs\wfastcgi.log" -ForegroundColor White
Write-Host ""
Write-Host "IMPORTANT: Since you're using a non-standard port ($port), users will need to" -ForegroundColor Yellow
Write-Host "include the port number in the URL: http://$hostname`:$port" -ForegroundColor Yellow
Write-Host "Alternatively, set up a reverse proxy or URL rewrite rule to use port 80." -ForegroundColor Yellow
Write-Host ""
