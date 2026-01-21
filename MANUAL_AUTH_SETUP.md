# Manual Windows Authentication Setup

The automated script had some issues configuring Windows Authentication. Follow these manual steps:

## Steps to Configure Windows Authentication

1. **Open IIS Manager**
   - Press `Win + R`, type `inetmgr`, press Enter
   - Or search for "Internet Information Services (IIS) Manager"

2. **Navigate to Your Site**
   - In the left panel, expand your server name
   - Expand "Sites"
   - Click on "ZiebartOnboarding"

3. **Open Authentication Settings**
   - In the center panel, double-click "Authentication"

4. **Configure Authentication**
   - **Disable Anonymous Authentication:**
     - Right-click "Anonymous Authentication"
     - Select "Disable"
   
   - **Enable Windows Authentication:**
     - Right-click "Windows Authentication"
     - Select "Enable"

5. **Verify Configuration**
   - Anonymous Authentication should show "Disabled"
   - Windows Authentication should show "Enabled"

## Verify Website Status

1. In IIS Manager, select "ZiebartOnboarding" site
2. In the right panel, click "Browse Website" or check the "State" column
3. The site should show as "Started"

## Test the Application

1. Open a web browser
2. Navigate to: `http://ziebartonboarding.com`
3. You should be prompted for Windows credentials
4. After authentication, you should see the onboarding dashboard

## Troubleshooting

### If the site shows as "Stopped":
1. Right-click "ZiebartOnboarding" site
2. Select "Start"

### If you get a 500 error:
1. Check the application pool status:
   - Expand "Application Pools"
   - Find "ZiebartOnboardingAppPool"
   - Ensure it shows "Started"
   - If not, right-click and select "Start"

2. Check logs:
   - Location: `C:\Websites\NewHireApp\logs\wfastcgi.log`
   - Look for Python errors

### If Windows Authentication doesn't work:
1. Ensure Windows Authentication feature is installed:
   - Open "Turn Windows features on or off"
   - Navigate to: Internet Information Services > World Wide Web Services > Security
   - Ensure "Windows Authentication" is checked
   - Click OK and restart if needed

2. Verify in IIS Manager:
   - Select the server (root) in IIS Manager
   - Double-click "Authentication"
   - Ensure "Windows Authentication" is available (not grayed out)

## Quick PowerShell Commands

To check site status:
```powershell
Get-Website -Name ZiebartOnboarding
```

To start the site:
```powershell
Start-Website -Name ZiebartOnboarding
```

To check application pool:
```powershell
Get-WebAppPoolState -Name ZiebartOnboardingAppPool
```

To start application pool:
```powershell
Start-WebAppPool -Name ZiebartOnboardingAppPool
```
