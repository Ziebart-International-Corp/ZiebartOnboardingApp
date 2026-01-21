# Check current bindings for ZiebartOnboarding site
Import-Module WebAdministration -ErrorAction SilentlyContinue

$siteName = "ZiebartOnboarding"

Write-Host "Current bindings for $siteName:" -ForegroundColor Cyan
$bindings = Get-WebBinding -Name $siteName
foreach ($binding in $bindings) {
    Write-Host "  $($binding.protocol) : $($binding.bindingInformation)" -ForegroundColor Yellow
}
