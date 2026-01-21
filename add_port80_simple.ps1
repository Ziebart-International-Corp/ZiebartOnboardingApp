# Simple script to add port 80 binding
# Run as Administrator

Import-Module WebAdministration -ErrorAction SilentlyContinue

$siteName = "ZiebartOnboarding"
$hostname = "ziebartonboarding.com"
$port = 80

# Check if binding already exists
$existing = Get-WebBinding -Name $siteName | Where-Object { 
    $_.bindingInformation -like "*:${port}:${hostname}" 
}

if ($existing) {
    Write-Host "Port 80 binding already exists!" -ForegroundColor Green
    exit 0
}

# Add the binding
try {
    New-WebBinding -Name $siteName -Protocol http -HostHeader $hostname -Port $port
    Write-Host "Port 80 binding added successfully!" -ForegroundColor Green
    
    # Restart site
    Stop-Website -Name $siteName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-Website -Name $siteName -ErrorAction SilentlyContinue
    
    Write-Host "Site restarted. You can now access http://ziebartonboarding.com" -ForegroundColor Cyan
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Message -like "*already*") {
        Write-Host "Port 80 may be in use by another site." -ForegroundColor Yellow
    }
}
