# Quick Fix for 404 Error on ziebartonboarding.com

## The Problem

You're getting a 404 when accessing `http://ziebartonboarding.com` because:
- The site is configured on port **8080**
- You're accessing it on port **80** (default HTTP port)
- There's no binding for port 80

## Solution Options

### Option 1: Use Port 8080 (Quickest)

Just add `:8080` to the URL:
```
http://ziebartonboarding.com:8080
```

### Option 2: Add Port 80 Binding (No Port Needed)

**Run this as Administrator:**

```powershell
cd C:\Websites\NewHireApp
.\add_port80_binding.ps1
```

This will let you access `http://ziebartonboarding.com` without the port number.

**Or manually in IIS Manager:**

1. Open IIS Manager (`inetmgr`)
2. Expand **Sites** → Click **ZiebartOnboarding**
3. Click **Bindings...** in the right pane
4. Click **Add...**
5. Fill in:
   - **Type:** http
   - **Host name:** ziebartonboarding.com
   - **Port:** 80
6. Click **OK**
7. Restart the site

## If Port 80 is Already in Use

If another site is using port 80, you'll get an error. In that case:
- Use port 8080: `http://ziebartonboarding.com:8080`
- Or move the other site to a different port first

## After Adding Port 80 Binding

Once you add the binding, both URLs will work:
- `http://ziebartonboarding.com` (port 80)
- `http://ziebartonboarding.com:8080` (port 8080)

## Still Getting 404?

If you still get a 404 after adding the binding, check:

1. **FastCGI Handler:**
   ```powershell
   .\register_fastcgi.ps1
   ```

2. **Check the log:**
   ```powershell
   Get-Content C:\Websites\NewHireApp\logs\wfastcgi.log -Tail 30
   ```

3. **Test localhost first:**
   ```
   http://localhost:8080
   ```
   If this works, it's a binding issue. If it doesn't, it's an app configuration issue.
