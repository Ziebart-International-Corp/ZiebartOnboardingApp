# Fix 404 Error When Port 80 Binding Exists

## The Problem

You have the port 80 binding configured, but you're still getting a 404 error. This means:
- ✅ DNS is working (request reaches server)
- ✅ IIS is routing to the correct site (binding works)
- ❌ FastCGI isn't processing the request (404 = handler not found)

## Root Cause

The FastCGI application needs to be registered at the **server level** in IIS, not just in `web.config`. The `web.config` tells IIS to use FastCGI, but IIS needs to know where the FastCGI application is registered.

## Solution: Register FastCGI at Server Level

**Run this as Administrator:**

```powershell
cd C:\Websites\NewHireApp
.\register_fastcgi.ps1
```

This script will:
1. Register the Python FastCGI application globally in IIS
2. Set environment variables (PYTHONPATH, WSGI_HANDLER, etc.)
3. Restart IIS

## After Running the Script

1. **Test localhost:**
   ```
   http://localhost:8080
   ```

2. **Test the domain:**
   ```
   http://ziebartonboarding.com
   http://ziebartonboarding.com:8080
   ```

## If It Still Doesn't Work

Check the wfastcgi log for errors:
```powershell
Get-Content C:\Websites\NewHireApp\logs\wfastcgi.log -Tail 30
```

If you see errors about "scriptProcessor could not be found", FastCGI isn't registered correctly.

## Manual Registration (Alternative)

If the script doesn't work, register manually in IIS Manager:

1. Open IIS Manager
2. Click your **server name** (INTERNALAPPS) in the left pane
3. Double-click **FastCGI Settings**
4. Click **Add Application...** in the right pane
5. Fill in:
   - **Full Path:** `C:\Websites\NewHireApp\venv\Scripts\python.exe`
   - **Arguments:** `C:\Websites\NewHireApp\venv\Lib\site-packages\wfastcgi.py`
   - **Max Instances:** `4`
6. Click **OK**
7. Select the FastCGI application you just created
8. Click **Edit...** → **Environment Variables**
9. Add these variables:
   - `PYTHONPATH` = `C:\Websites\NewHireApp`
   - `WSGI_HANDLER` = `app.app`
   - `WSGI_LOG` = `C:\Websites\NewHireApp\logs\wfastcgi.log`
10. Click **OK** and restart IIS (`iisreset`)
