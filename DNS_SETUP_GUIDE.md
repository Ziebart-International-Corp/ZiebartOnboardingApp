# DNS Configuration Guide for ziebartonboarding.com

## Current Status

✅ **Application is working** - `localhost:8080` works  
❌ **DNS not configured** - `ziebartonboarding.com:8080` cannot be resolved

## What You Need to Do

Configure DNS to point `ziebartonboarding.com` to your server's IP address.

## Step 1: Find Your Server's IP Address

Run this command in PowerShell to find your server's IP:
```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object IPAddress, InterfaceAlias
```

Or check in Windows:
- Open Network Settings
- Look for your network adapter
- Find the IPv4 address (usually something like 192.168.x.x or 10.x.x.x)

## Step 2: Configure DNS

You need to add DNS records for `ziebartonboarding.com`. This depends on where your domain is registered:

### Option A: If you manage DNS yourself (e.g., GoDaddy, Namecheap, etc.)

1. Log into your domain registrar's DNS management panel
2. Add an **A Record**:
   - **Name/Host:** `@` or `ziebartonboarding.com` (or leave blank)
   - **Type:** A
   - **Value/Points to:** Your server's IP address (from Step 1)
   - **TTL:** 3600 (or default)

3. (Optional) Add a **CNAME Record** for www:
   - **Name/Host:** `www`
   - **Type:** CNAME
   - **Value/Points to:** `ziebartonboarding.com`
   - **TTL:** 3600

### Option B: If using Active Directory DNS (Internal Network)

1. Open **DNS Manager** (dnsmgmt.msc)
2. Navigate to your domain's Forward Lookup Zone
3. Right-click → **New Host (A or AAAA)**
4. Enter:
   - **Name:** `ziebartonboarding` (or leave blank for root)
   - **IP address:** Your server's IP address
   - Check "Create associated pointer (PTR) record" if desired
5. Click **Add Host**

### Option C: If using Windows Server DNS

1. Open **DNS Manager**
2. Expand your domain
3. Right-click on the domain → **New Host (A or AAAA)**
4. Enter the hostname and IP address
5. Click **Add Host**

## Step 3: Wait for DNS Propagation

- **Internal DNS:** Usually immediate (may need to flush DNS cache)
- **External DNS:** Can take 5 minutes to 48 hours (usually 15-30 minutes)

## Step 4: Test DNS Resolution

After configuring DNS, test it:

**On the server:**
```powershell
nslookup ziebartonboarding.com
```

**From another computer:**
```powershell
ping ziebartonboarding.com
```

The IP address returned should match your server's IP.

## Step 5: Flush DNS Cache (if needed)

If DNS is configured but still not resolving:

**On Windows:**
```powershell
ipconfig /flushdns
```

**On the server:**
```powershell
Clear-DnsClientCache
```

## Testing Without DNS

Until DNS is configured, you can test using:

1. **Localhost:** `http://localhost:8080` ✅ (This works!)
2. **Server IP:** `http://[your-server-ip]:8080`
3. **Server hostname:** `http://[server-name]:8080`

## Troubleshooting

### If DNS is configured but still not working:

1. **Check firewall:**
   - Ensure port 8080 is open in Windows Firewall
   - Allow inbound connections on port 8080

2. **Check IIS bindings:**
   - Open IIS Manager
   - Select "ZiebartOnboarding" site
   - Click "Bindings..."
   - Verify there's a binding for port 8080 with hostname `ziebartonboarding.com`

3. **Test from server itself:**
   ```powershell
   # Add to hosts file for testing (temporary)
   Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 ziebartonboarding.com"
   ```
   Then try `http://ziebartonboarding.com:8080` from the server

4. **Check IIS site status:**
   - Ensure the site is "Started" in IIS Manager

## Important Notes

- **Port 8080:** Users will need to include `:8080` in the URL until you set up a reverse proxy or use port 80
- **Internal vs External:** If this is for internal use only, configure internal DNS. If external, configure public DNS.
- **SSL/HTTPS:** For production, you'll want to set up SSL certificates and use HTTPS on port 443

## Quick Test Commands

```powershell
# Check if DNS resolves
Resolve-DnsName ziebartonboarding.com

# Test connectivity
Test-NetConnection -ComputerName ziebartonboarding.com -Port 8080

# Check IIS bindings
Get-WebBinding -Name ZiebartOnboarding
```
