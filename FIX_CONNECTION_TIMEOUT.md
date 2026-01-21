# Fix Connection Timeout Error

## The Problem

You're getting `ERR_CONNECTION_TIMED_OUT` when accessing `192.168.0.93:8080`. This means the request isn't reaching the server or the server isn't responding.

## Common Causes

1. **IIS Site is Stopped**
2. **Application Pool is Stopped**
3. **Windows Firewall is Blocking Port 8080**
4. **Binding Configuration Issue**

## Quick Fix Steps

### Step 1: Check IIS Site Status (Run as Administrator)

**In IIS Manager:**
1. Open IIS Manager (`inetmgr`)
2. Expand **Sites** in the left pane
3. Look for **ZiebartOnboarding**
4. Check if it says **"Started"** or **"Stopped"**
5. If stopped, right-click → **Manage Website** → **Start**

**Or in PowerShell (as Admin):**
```powershell
Import-Module WebAdministration
Get-Website -Name ZiebartOnboarding | Select-Object Name, State
Start-Website -Name ZiebartOnboarding  # If stopped
```

### Step 2: Check Application Pool (Run as Administrator)

**In IIS Manager:**
1. Click **Application Pools** in the left pane
2. Look for **ZiebartOnboardingAppPool**
3. Check if it says **"Started"** or **"Stopped"**
4. If stopped, right-click → **Start**

**Or in PowerShell (as Admin):**
```powershell
Get-WebAppPool -Name ZiebartOnboardingAppPool | Select-Object Name, State
Start-WebAppPool -Name ZiebartOnboardingAppPool  # If stopped
```

### Step 3: Check Windows Firewall (Run as Administrator)

**In Windows Firewall:**
1. Open **Windows Defender Firewall with Advanced Security**
2. Click **Inbound Rules** in the left pane
3. Look for a rule allowing port 8080
4. If not found, create one:
   - Click **New Rule...**
   - Select **Port** → Next
   - Select **TCP** and enter **8080** → Next
   - Select **Allow the connection** → Next
   - Check all profiles → Next
   - Name it "IIS Port 8080" → Finish

**Or in PowerShell (as Admin):**
```powershell
# Check existing rules
Get-NetFirewallRule | Where-Object { $_.DisplayName -match "8080" }

# Add firewall rule
New-NetFirewallRule -DisplayName "IIS Port 8080" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
```

### Step 4: Test from Server Itself

**On the server, test localhost first:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing
```

If this works, the app is fine - it's a firewall or binding issue.
If this doesn't work, the app has a problem.

## Automated Fix Script

Run this as Administrator:

```powershell
cd C:\Websites\NewHireApp
.\check_firewall_and_site.ps1
```

This script will:
- Check if the site is running and start it if needed
- Check if the app pool is running and start it if needed
- Check firewall and add a rule if needed
- Test localhost connection

## After Fixing

Once you've:
1. Started the IIS site
2. Started the application pool
3. Added firewall rule for port 8080

Test from your computer:
- `http://192.168.0.93:8080`
- `http://ziebartonboarding.com:8080`
- `http://ziebartonboarding.com`

## Still Not Working?

If you still get timeouts after fixing the above:

1. **Check if port 8080 is listening:**
   ```powershell
   netstat -an | findstr :8080
   ```
   You should see `LISTENING` for port 8080

2. **Check wfastcgi log:**
   ```powershell
   Get-Content C:\Websites\NewHireApp\logs\wfastcgi.log -Tail 30
   ```

3. **Check Windows Event Viewer:**
   - Open Event Viewer
   - Check **Windows Logs** → **Application**
   - Look for IIS or Python errors
