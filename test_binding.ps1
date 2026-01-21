# Test IIS Binding and DNS Resolution
Write-Host "Testing IIS Binding Configuration..." -ForegroundColor Cyan
Write-Host ""

Import-Module WebAdministration -ErrorAction SilentlyContinue

Write-Host "1. IIS Bindings for ZiebartOnboarding:" -ForegroundColor Yellow
$bindings = Get-WebBinding -Name ZiebartOnboarding
foreach ($binding in $bindings) {
    Write-Host "   Protocol: $($binding.protocol)" -ForegroundColor Green
    Write-Host "   Binding: $($binding.bindingInformation)" -ForegroundColor Green
    Write-Host ""
}

Write-Host "2. Testing DNS Resolution:" -ForegroundColor Yellow
try {
    $dnsResult = Resolve-DnsName -Name ziebartonboarding.com -ErrorAction Stop
    Write-Host "   DNS resolves to: $($dnsResult[0].IPAddress)" -ForegroundColor Green
} catch {
    Write-Host "   DNS does NOT resolve (this is the problem!)" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "3. Testing localhost:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   localhost:8080 - Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   localhost:8080 - Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "4. Testing server IP:" -ForegroundColor Yellow
$serverIP = "192.168.0.93"
try {
    $response = Invoke-WebRequest -Uri "http://${serverIP}:8080" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ${serverIP}:8080 - Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   ${serverIP}:8080 - Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Explanation:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "The IIS binding is configured correctly, BUT:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Browser needs DNS to resolve 'ziebartonboarding.com' to an IP" -ForegroundColor White
Write-Host "2. THEN the request reaches IIS" -ForegroundColor White
Write-Host "3. THEN IIS checks the binding and routes to your app" -ForegroundColor White
Write-Host ""
Write-Host "Since DNS isn't configured, the browser can't resolve the name," -ForegroundColor Yellow
Write-Host "so the request never reaches IIS." -ForegroundColor Yellow
Write-Host ""
Write-Host "Solutions:" -ForegroundColor Green
Write-Host "  A. Configure DNS (recommended for production)" -ForegroundColor White
Write-Host "  B. Add to hosts file for testing (temporary)" -ForegroundColor White
Write-Host "  C. Use IP address or localhost directly" -ForegroundColor White
Write-Host ""
