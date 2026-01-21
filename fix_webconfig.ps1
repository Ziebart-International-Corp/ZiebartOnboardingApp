# Fix web.config Authentication Issues
# Run as Administrator

Write-Host "Fixing web.config authentication configuration..." -ForegroundColor Cyan
Write-Host ""

$webConfigPath = "C:\Websites\NewHireApp\web.config"
$backupPath = "C:\Websites\NewHireApp\web.config.backup"

# Backup web.config
Write-Host "1. Creating backup of web.config..." -ForegroundColor Yellow
Copy-Item $webConfigPath $backupPath -Force
Write-Host "   Backup created: $backupPath" -ForegroundColor Green

# Read current web.config
Write-Host "2. Reading web.config..." -ForegroundColor Yellow
[xml]$xml = Get-Content $webConfigPath

# Remove authentication section from web.config (we'll configure it in IIS instead)
Write-Host "3. Removing authentication section from web.config..." -ForegroundColor Yellow
$authNode = $xml.SelectSingleNode("//system.webServer/authentication")
if ($authNode) {
    $authNode.ParentNode.RemoveChild($authNode) | Out-Null
    Write-Host "   Authentication section removed" -ForegroundColor Green
} else {
    Write-Host "   Authentication section not found (already removed)" -ForegroundColor Gray
}

# Save updated web.config
Write-Host "4. Saving updated web.config..." -ForegroundColor Yellow
$xml.Save($webConfigPath)
Write-Host "   web.config updated" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "web.config Fixed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Open IIS Manager" -ForegroundColor White
Write-Host "2. Navigate to: Sites > ZiebartOnboarding" -ForegroundColor White
Write-Host "3. Double-click 'Authentication'" -ForegroundColor White
Write-Host "4. Enable 'Windows Authentication'" -ForegroundColor White
Write-Host "5. Disable 'Anonymous Authentication'" -ForegroundColor White
Write-Host ""
Write-Host "The authentication settings are now managed in IIS Manager instead of web.config" -ForegroundColor Cyan
Write-Host "This should resolve the error you were seeing." -ForegroundColor Cyan
Write-Host ""
