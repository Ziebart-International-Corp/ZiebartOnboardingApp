# Add ziebartonboarding.com to hosts file for testing
# This allows the domain to work without DNS configuration
# Run as Administrator

Write-Host "Adding ziebartonboarding.com to hosts file..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$hostname = "ziebartonboarding.com"
$ipAddress = "127.0.0.1"  # localhost

# Check if entry already exists
$hostsContent = Get-Content $hostsPath -ErrorAction SilentlyContinue
$entryExists = $hostsContent | Where-Object { $_ -match "ziebartonboarding\.com" }

if ($entryExists) {
    Write-Host "Entry already exists in hosts file:" -ForegroundColor Yellow
    Write-Host "  $entryExists" -ForegroundColor Gray
    Write-Host ""
    $response = Read-Host "Do you want to remove it? (y/n)"
    if ($response -eq 'y' -or $response -eq 'Y') {
        $newContent = $hostsContent | Where-Object { $_ -notmatch "ziebartonboarding\.com" }
        $newContent | Set-Content $hostsPath -Encoding ASCII
        Write-Host "Entry removed." -ForegroundColor Green
    }
    exit 0
}

# Add entry
try {
    $entry = "$ipAddress`t$hostname"
    Add-Content -Path $hostsPath -Value $entry -Encoding ASCII -ErrorAction Stop
    Write-Host "Successfully added to hosts file:" -ForegroundColor Green
    Write-Host "  $entry" -ForegroundColor Gray
    Write-Host ""
    Write-Host "You can now access: http://ziebartonboarding.com:8080" -ForegroundColor Green
    Write-Host ""
    Write-Host "Note: This only works on THIS computer." -ForegroundColor Yellow
    Write-Host "For other computers, you need to configure DNS." -ForegroundColor Yellow
} catch {
    Write-Host "ERROR: Failed to add entry: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
