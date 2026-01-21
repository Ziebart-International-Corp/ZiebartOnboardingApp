# Test if the Flask app is working directly
# This helps diagnose if it's a binding issue or app issue

Write-Host "Testing Flask Application..." -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Testing localhost:8080..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   Status: $($response.StatusCode) ✓" -ForegroundColor Green
    Write-Host "   Content Length: $($response.Content.Length) bytes" -ForegroundColor Gray
    if ($response.Content -match "Onboarding App" -or $response.Content -match "Dashboard") {
        Write-Host "   ✓ App is working correctly!" -ForegroundColor Green
    }
} catch {
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Host "   Status Code: $statusCode" -ForegroundColor Yellow
        
        if ($statusCode -eq 401) {
            Write-Host "   Note: 401 Unauthorized is expected with Windows Auth" -ForegroundColor Gray
            Write-Host "   The app is responding, but authentication is required." -ForegroundColor Gray
        } elseif ($statusCode -eq 404) {
            Write-Host "   ✗ 404 means the app isn't handling the request" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "2. Testing localhost:8080/app.py..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080/app.py" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "   Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "3. Testing ziebartonboarding.com:8080..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://ziebartonboarding.com:8080" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "   Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "4. Testing ziebartonboarding.com (port 80)..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://ziebartonboarding.com" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   Status: $($response.StatusCode) ✓" -ForegroundColor Green
} catch {
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Host "   Status Code: $statusCode" -ForegroundColor Yellow
        
        if ($statusCode -eq 404) {
            Write-Host ""
            Write-Host "   DIAGNOSIS: Port 80 binding exists but app returns 404" -ForegroundColor Red
            Write-Host "   This means:" -ForegroundColor Yellow
            Write-Host "     - IIS is routing to the site ✓" -ForegroundColor Gray
            Write-Host "     - But FastCGI/URL Rewrite isn't working ✗" -ForegroundColor Gray
            Write-Host ""
            Write-Host "   Solutions:" -ForegroundColor Cyan
            Write-Host "     1. Check FastCGI registration: .\register_fastcgi.ps1" -ForegroundColor White
            Write-Host "     2. Check web.config URL rewrite rules" -ForegroundColor White
            Write-Host "     3. Check wfastcgi.log for errors" -ForegroundColor White
        }
    }
}

Write-Host ""
