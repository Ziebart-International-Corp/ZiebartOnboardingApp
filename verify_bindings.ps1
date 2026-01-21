Import-Module WebAdministration
$siteName = "ZiebartOnboarding"
Write-Host "Bindings for $siteName :" -ForegroundColor Cyan
Get-WebBinding -Name $siteName | ForEach-Object {
    Write-Host "  $($_.protocol) - $($_.bindingInformation)" -ForegroundColor Yellow
}
