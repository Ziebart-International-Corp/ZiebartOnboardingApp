# Pull latest main from GitHub and restart the IIS app pool for Ziebart Onboarding.
# Double-click the desktop shortcut (or run this script as Administrator).

$ErrorActionPreference = 'Stop'

$repoPath = 'C:\Websites\NewHireApp'
$appPoolName = 'ZiebartOnboardingAppPool'
$branch = 'main'
$venvPython = Join-Path $repoPath 'venv\Scripts\python.exe'

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal] $identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host 'Requesting Administrator privileges...' -ForegroundColor Yellow
    $args = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath
    )
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $args
    exit 0
}

Write-Host '========================================' -ForegroundColor Cyan
Write-Host 'Ziebart Onboarding - Pull and Restart' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

Set-Location $repoPath

Write-Host "Pulling origin/$branch in $repoPath ..." -ForegroundColor Yellow
git pull origin $branch
if ($LASTEXITCODE -ne 0) {
    throw "git pull failed with exit code $LASTEXITCODE"
}
Write-Host 'Git pull completed.' -ForegroundColor Green
Write-Host ''

if (-not (Test-Path $venvPython)) {
    throw "Python venv not found at $venvPython"
}

Write-Host 'Installing/updating Python requirements in venv ...' -ForegroundColor Yellow
& $venvPython -m pip install -r (Join-Path $repoPath 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed with exit code $LASTEXITCODE"
}
Write-Host 'Requirements installed.' -ForegroundColor Green
Write-Host ''

Write-Host 'Verifying app import ...' -ForegroundColor Yellow
& $venvPython -c "import app; print('import ok')"
if ($LASTEXITCODE -ne 0) {
    throw "app import failed - fix the error above before restarting IIS"
}
Write-Host 'App import OK.' -ForegroundColor Green
Write-Host ''

Import-Module WebAdministration -ErrorAction Stop

Write-Host "Restarting IIS app pool: $appPoolName ..." -ForegroundColor Yellow
Restart-WebAppPool -Name $appPoolName
Start-Sleep -Seconds 2

$pool = Get-WebAppPoolState -Name $appPoolName
Write-Host "App pool state: $($pool.Value)" -ForegroundColor Green
Write-Host ''
Write-Host 'Done. The site is running the latest code from GitHub main.' -ForegroundColor Green
Write-Host ''
Read-Host 'Press Enter to close'
