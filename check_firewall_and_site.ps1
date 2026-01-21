# Check IIS Site Status and Windows Firewall
# Run as Administrator

Write-Host "Checking IIS Site and Firewall Configuration..." -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "WARNING: Not running as Administrator - some checks may fail" -ForegroundColor Yellow
    Write-Host ""
}

Import-Module WebAdministration -ErrorAction SilentlyContinue

Write-Host "1. Checking IIS Site Status..." -ForegroundColor Yellow
$siteName = "ZiebartOnboarding"
$site = Get-Website -Name $siteName -ErrorAction SilentlyContinue

if ($site) {
    Write-Host "   Site found: $siteName" -ForegroundColor Green
    Write-Host "   State: $($site.State)" -ForegroundColor $(if ($site.State -eq 'Started') { 'Green' } else { 'Red' })
    
    if ($site.State -ne 'Started') {
        Write-Host ""
        Write-Host "   SITE IS NOT RUNNING!" -ForegroundColor Red
        Write-Host "   Starting site..." -ForegroundColor Yellow
        try {
            Start-Website -Name $siteName -ErrorAction Stop
            Write-Host "   Site started" -ForegroundColor Green
        } catch {
            Write-Host "   Failed to start site: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "   Bindings:" -ForegroundColor Gray
    $bindings = Get-WebBinding -Name $siteName
    foreach ($binding in $bindings) {
        Write-Host "     $($binding.protocol) : $($binding.bindingInformation)" -ForegroundColor Cyan
    }
} else {
    Write-Host "   Site '$siteName' not found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "2. Checking Application Pool..." -ForegroundColor Yellow
if ($site) {
    $appPoolName = (Get-Item "IIS:\Sites\$siteName").applicationPool
    $appPool = Get-Item "IIS:\AppPools\$appPoolName" -ErrorAction SilentlyContinue
    
    if ($appPool) {
        Write-Host "   App Pool: $appPoolName" -ForegroundColor Gray
        Write-Host "   State: $($appPool.State)" -ForegroundColor $(if ($appPool.State -eq 'Started') { 'Green' } else { 'Red' })
        
        if ($appPool.State -ne 'Started') {
            Write-Host ""
            Write-Host "   APPLICATION POOL IS NOT RUNNING!" -ForegroundColor Red
            Write-Host "   Starting app pool..." -ForegroundColor Yellow
            try {
                Start-WebAppPool -Name $appPoolName -ErrorAction Stop
                Write-Host "   App pool started" -ForegroundColor Green
            } catch {
                Write-Host "   Failed to start app pool: $($_.Exception.Message)" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "   App pool not found!" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "3. Checking Windows Firewall..." -ForegroundColor Yellow
if ($isAdmin) {
    $port8080Rule = $null
    try {
        $rulesByName = Get-NetFirewallRule -DisplayName "*8080*" -ErrorAction SilentlyContinue
        if ($rulesByName) {
            $port8080Rule = $rulesByName
        } else {
            $allRules = Get-NetFirewallRule -ErrorAction SilentlyContinue
            foreach ($rule in $allRules) {
                $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
                if ($portFilter -and $portFilter.LocalPort -eq 8080) {
                    $port8080Rule = $rule
                    break
                }
            }
        }
    } catch {
        Write-Host "   Could not check firewall rules: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    if ($port8080Rule) {
        Write-Host "   Firewall rules for port 8080 found:" -ForegroundColor Green
        if ($port8080Rule -is [array]) {
            foreach ($rule in $port8080Rule) {
                Write-Host "     $($rule.DisplayName) - Enabled: $($rule.Enabled)" -ForegroundColor Gray
            }
        } else {
            Write-Host "     $($port8080Rule.DisplayName) - Enabled: $($port8080Rule.Enabled)" -ForegroundColor Gray
        }
    } else {
        Write-Host "   No firewall rule found for port 8080!" -ForegroundColor Yellow
        Write-Host "   This might be blocking connections." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   Adding firewall rule..." -ForegroundColor Yellow
        try {
            New-NetFirewallRule -DisplayName "IIS Port 8080" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow -ErrorAction Stop
            Write-Host "   Firewall rule added for port 8080" -ForegroundColor Green
        } catch {
            Write-Host "   Failed to add firewall rule: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "   You may need to add it manually in Windows Firewall" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "   Cannot check firewall (not running as Administrator)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "4. Testing localhost connection..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   localhost:8080 - Status: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "   localhost:8080 - Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "   Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If you're getting connection timeouts:" -ForegroundColor Yellow
Write-Host "  1. Make sure IIS site is Started" -ForegroundColor White
Write-Host "  2. Make sure Application Pool is Started" -ForegroundColor White
Write-Host "  3. Make sure Windows Firewall allows port 8080" -ForegroundColor White
Write-Host "  4. Try accessing from the server itself first (localhost)" -ForegroundColor White
Write-Host ""
