# Troubleshooting 404 Error on ziebartonboarding.com

## The Issue

You're getting a 404 error when accessing `ziebartonboarding.com`. This means:
- ✅ DNS is working (request reaches IIS)
- ✅ IIS is routing to the correct site (ZiebartOnboarding)
- ❌ The Flask application isn't handling the request

## Possible Causes

### 1. Wrong Port (Most Likely)

If you're accessing `ziebartonboarding.com` (no port), you're using port **80** (default HTTP port).

But your site is configured on port **8080**.

**Solution:** Access it with the port number:
```
http://ziebartonboarding.com:8080
```

### 2. Need Binding on Port 80

If you want to access it without the port number, add a binding on port 80:

**In IIS Manager:**
1. Open IIS Manager
2. Select **ZiebartOnboarding** site
3. Click **Bindings...**
4. Click **Add...**
5. Type: **http**
6. Host name: **ziebartonboarding.com**
7. Port: **80**
8. Click **OK**

**Or use PowerShell (as Admin):**
```powershell
New-WebBinding -Name ZiebartOnboarding -Protocol http -HostHeader ziebartonboarding.com -Port 80
```

### 3. FastCGI Handler Not Working

Check if FastCGI is processing requests:

**Check the log:**
```powershell
Get-Content C:\Websites\NewHireApp\logs\wfastcgi.log -Tail 50
```

If you see errors, the FastCGI handler might not be registered correctly.

### 4. URL Rewrite Not Working

The `web.config` has URL rewrite rules. If they're not working, requests won't reach `app.py`.

**Test:** Try accessing `http://ziebartonboarding.com:8080/app.py` directly.

## Quick Fix

**Option A: Use Port 8080**
```
http://ziebartonboarding.com:8080
```

**Option B: Add Port 80 Binding**
Run this as Administrator:
```powershell
cd C:\Websites\NewHireApp
.\add_port80_binding.ps1
```

## Testing Steps

1. **Test localhost:**
   ```
   http://localhost:8080
   ```
   If this works, the app is fine, just need the right binding.

2. **Test with IP:**
   ```
   http://192.168.0.93:8080
   ```
   If this works, DNS/binding is the issue.

3. **Test with hostname and port:**
   ```
   http://ziebartonboarding.com:8080
   ```
   If this works, you just need to add port 80 binding.
