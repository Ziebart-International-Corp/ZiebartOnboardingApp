# Register FastCGI Application for IIS
# Run as Administrator

Write-Host "Registering FastCGI Application..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

$pythonExe = "C:\Websites\NewHireApp\venv\Scripts\python.exe"
$wfastcgi = "C:\Websites\NewHireApp\venv\Lib\site-packages\wfastcgi.py"

# Check if files exist
if (-not (Test-Path $pythonExe)) {
    Write-Host "ERROR: Python executable not found: $pythonExe" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $wfastcgi)) {
    Write-Host "ERROR: wfastcgi.py not found: $wfastcgi" -ForegroundColor Red
    exit 1
}

Write-Host "Python executable: $pythonExe" -ForegroundColor Gray
Write-Host "wfastcgi.py: $wfastcgi" -ForegroundColor Gray
Write-Host ""

Import-Module WebAdministration -ErrorAction SilentlyContinue

Write-Host "Step 1: Checking for existing FastCGI application..." -ForegroundColor Yellow
try {
    # Try multiple methods to find existing FastCGI application
    $existing = $null
    
    # Method 1: Check by fullPath
    try {
        $existing = Get-WebConfiguration -Filter "system.webServer/fastCgi/application[@fullPath='$pythonExe']" -ErrorAction Stop
    } catch {
        # Method 2: Get all and filter
        $allApps = Get-WebConfiguration -Filter "system.webServer/fastCgi/application" -ErrorAction SilentlyContinue
        if ($allApps) {
            $existing = $allApps | Where-Object { $_.fullPath -eq $pythonExe -and $_.arguments -eq $wfastcgi }
        }
    }
    
    if ($existing) {
        Write-Host "  Existing FastCGI application found" -ForegroundColor Yellow
        Write-Host "  Full Path: $($existing.fullPath)" -ForegroundColor Gray
        Write-Host "  Arguments: $($existing.arguments)" -ForegroundColor Gray
        
        # Check if environment variables are set
        $envVars = Get-WebConfiguration -Filter "system.webServer/fastCgi/application[@fullPath='$pythonExe']/environmentVariables" -ErrorAction SilentlyContinue
        if ($envVars) {
            Write-Host "  Environment variables already configured" -ForegroundColor Green
            Write-Host "  FastCGI is already registered correctly!" -ForegroundColor Green
            Write-Host ""
            Write-Host "Skipping registration - FastCGI is already set up." -ForegroundColor Cyan
            Write-Host ""
            Write-Host "If you're still getting 404 errors, check:" -ForegroundColor Yellow
            Write-Host "  1. IIS site bindings" -ForegroundColor Gray
            Write-Host "  2. web.config handler configuration" -ForegroundColor Gray
            Write-Host "  3. wfastcgi.log for errors" -ForegroundColor Gray
            exit 0
        } else {
            Write-Host "  Environment variables missing - will add them" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  No existing FastCGI application found" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Could not check for existing application: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  Will attempt to add anyway..." -ForegroundColor Gray
}

Write-Host "Step 2: Adding/Updating FastCGI application..." -ForegroundColor Yellow
try {
    # Check if it already exists before adding
    $alreadyExists = $false
    try {
        $check = Get-WebConfiguration -Filter "system.webServer/fastCgi/application[@fullPath='$pythonExe' and @arguments='$wfastcgi']" -ErrorAction Stop
        if ($check) {
            $alreadyExists = $true
            Write-Host "  FastCGI application already exists, skipping add..." -ForegroundColor Yellow
        }
    } catch {
        # Doesn't exist, will add
    }
    
    if (-not $alreadyExists) {
        Add-WebConfiguration -Filter "system.webServer/fastCgi" -Value @{
            fullPath = $pythonExe
            arguments = $wfastcgi
            maxInstances = 4
            idleTimeout = 1800
            activityTimeout = 30
            requestTimeout = 90
            instanceMaxRequests = 10000
            protocol = "NamedPipe"
            flushNamedPipe = $false
        } -ErrorAction Stop
        
        Write-Host "  FastCGI application added successfully" -ForegroundColor Green
    } else {
        Write-Host "  FastCGI application already exists, using existing registration" -ForegroundColor Green
    }
} catch {
    if ($_.Exception.Message -match "duplicate") {
        Write-Host "  FastCGI application already exists (duplicate error)" -ForegroundColor Yellow
        Write-Host "  This is OK - will proceed to configure environment variables" -ForegroundColor Gray
    } else {
        Write-Host "  ERROR: Failed to add FastCGI application" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Will try to continue with environment variables..." -ForegroundColor Yellow
    }
}

Write-Host "Step 3: Configuring environment variables..." -ForegroundColor Yellow

# Check which environment variables already exist
$existingEnvVars = Get-WebConfiguration -Filter "system.webServer/fastCgi/application[@fullPath='$pythonExe']/environmentVariables" -ErrorAction SilentlyContinue
$existingVarNames = @()
if ($existingEnvVars) {
    $existingVarNames = $existingEnvVars | ForEach-Object { $_.name }
}

$envVarsToAdd = @(
    @{name="PYTHONPATH"; value="C:\Websites\NewHireApp"},
    @{name="WSGI_HANDLER"; value="app.app"},
    @{name="WSGI_LOG"; value="C:\Websites\NewHireApp\logs\wfastcgi.log"}
)

$addedCount = 0
$skippedCount = 0

foreach ($envVar in $envVarsToAdd) {
    if ($existingVarNames -contains $envVar.name) {
        Write-Host "  $($envVar.name) already exists, skipping..." -ForegroundColor Gray
        $skippedCount++
    } else {
        try {
            Add-WebConfigurationProperty -Filter "system.webServer/fastCgi/application[@fullPath='$pythonExe']" -Name "environmentVariables" -Value $envVar -ErrorAction Stop
            Write-Host "  Added $($envVar.name) = $($envVar.value)" -ForegroundColor Green
            $addedCount++
        } catch {
            Write-Host "  WARNING: Could not add $($envVar.name)" -ForegroundColor Yellow
            Write-Host "    Error: $($_.Exception.Message)" -ForegroundColor Gray
        }
    }
}

if ($addedCount -gt 0) {
    Write-Host "  Environment variables configured: $addedCount added, $skippedCount already existed" -ForegroundColor Green
} else {
    Write-Host "  All environment variables already configured" -ForegroundColor Green
}

Write-Host "Step 4: Verifying FastCGI application..." -ForegroundColor Yellow
$fastcgiApp = Get-WebConfiguration -Filter "system.webServer/fastCgi/application[@fullPath='$pythonExe']" -ErrorAction SilentlyContinue
if ($fastcgiApp) {
    Write-Host "  FastCGI application verified" -ForegroundColor Green
    Write-Host "  Full Path: $($fastcgiApp.fullPath)" -ForegroundColor Gray
    Write-Host "  Arguments: $($fastcgiApp.arguments)" -ForegroundColor Gray
} else {
    Write-Host "  WARNING: FastCGI application not found after registration" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 5: Restarting IIS..." -ForegroundColor Yellow
try {
    iisreset /restart
    Write-Host "  IIS restarted successfully" -ForegroundColor Green
} catch {
    Write-Host "  Could not restart IIS automatically" -ForegroundColor Yellow
    Write-Host "  Please restart IIS manually: iisreset" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "FastCGI Registration Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Try accessing the application again: http://localhost:8080" -ForegroundColor White
Write-Host "2. If you still see errors, check the logs:" -ForegroundColor White
Write-Host "   C:\Websites\NewHireApp\logs\wfastcgi.log" -ForegroundColor White
Write-Host ""
