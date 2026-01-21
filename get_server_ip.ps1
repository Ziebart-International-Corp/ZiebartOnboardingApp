# Get Server IP Address for DNS Configuration
Write-Host "Finding server IP address..." -ForegroundColor Cyan
Write-Host ""

$ipAddresses = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { 
    $_.IPAddress -notlike '127.*' -and 
    $_.IPAddress -notlike '169.254.*' -and
    $_.PrefixOrigin -ne 'WellKnown'
} | Select-Object IPAddress, InterfaceAlias, PrefixLength

if ($ipAddresses) {
    Write-Host "Server IP Addresses:" -ForegroundColor Green
    Write-Host ""
    foreach ($ip in $ipAddresses) {
        Write-Host "  IP Address: $($ip.IPAddress)" -ForegroundColor Yellow
        Write-Host "  Interface: $($ip.InterfaceAlias)" -ForegroundColor Gray
        Write-Host "  Subnet: /$($ip.PrefixLength)" -ForegroundColor Gray
        Write-Host ""
    }
    Write-Host "Use one of these IP addresses for your DNS A record." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "DNS Configuration:" -ForegroundColor Yellow
    Write-Host "  Domain: ziebartonboarding.com" -ForegroundColor White
    Write-Host "  Type: A Record" -ForegroundColor White
    Write-Host "  Value: [Use one of the IP addresses above]" -ForegroundColor White
    Write-Host "  Port: 8080" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "Could not find IP address. Please check network settings." -ForegroundColor Red
}

# Also show hostname
$hostname = $env:COMPUTERNAME
Write-Host "Server Hostname: $hostname" -ForegroundColor Cyan
Write-Host ""
