# Fix IIS Binding to Route ziebartonboarding.com Correctly

## The Problem

When you access `ziebartonboarding.com:8080`, IIS is routing to the wrong site because:
- Multiple sites might be using port 8080
- The ZiebartOnboarding site might have a catch-all binding (port only, no hostname)
- IIS routes based on hostname when multiple sites share a port

## Solution: Run the Fix Script

**Run this as Administrator:**

```powershell
cd C:\Websites\NewHireApp
.\fix_hostname_binding.ps1
```

This script will:
1. Remove any port-only bindings (catch-all) on port 8080 for ZiebartOnboarding
2. Ensure only the hostname binding `ziebartonboarding.com:8080` exists
3. Restart the site

## Manual Fix (Alternative)

If you prefer to fix it manually in IIS Manager:

1. **Open IIS Manager** (run `inetmgr`)

2. **Expand Sites** → Click **ZiebartOnboarding**

3. **Click "Bindings..." in the right pane**

4. **Check the bindings:**
   - If you see `*:8080` (no hostname) → **Remove it**
   - You should only have `*:8080:ziebartonboarding.com` (with hostname)

5. **If the hostname binding doesn't exist:**
   - Click **Add...**
   - Type: **http**
   - Host name: **ziebartonboarding.com**
   - Port: **8080**
   - Click **OK**

6. **Click Close**

7. **Restart the site:**
   - Right-click **ZiebartOnboarding** → **Manage Website** → **Restart**

## How IIS Routing Works

When multiple sites share a port (like 8080), IIS uses this priority:

1. **Hostname match** - If a request comes with `Host: ziebartonboarding.com`, IIS looks for a site with that hostname binding
2. **Catch-all** - If no hostname matches, IIS uses the site with `*:8080` (no hostname specified)
3. **Default site** - If no match, goes to Default Web Site

## After Fixing

Once you remove the catch-all binding and keep only the hostname binding:
- ✅ `http://ziebartonboarding.com:8080` → Routes to ZiebartOnboarding
- ✅ `http://localhost:8080` → Might go to another site (if it has a catch-all)
- ✅ `http://[other-hostname]:8080` → Routes to the site with that hostname binding

## Testing

After fixing, test from your computer:
1. Make sure DNS resolves `ziebartonboarding.com` to the server IP (192.168.0.93)
2. Or add to your computer's hosts file: `192.168.0.93 ziebartonboarding.com`
3. Access: `http://ziebartonboarding.com:8080`
