# Ziebart Onboarding App - IIS Deployment Guide

## Prerequisites

1. **Windows Server** with IIS installed
2. **Python 3.13** installed
3. **ODBC Driver 18 for SQL Server** installed
4. **Administrator access** to the server
5. **DNS configuration** to point `ziebartonboarding.com` to your server's IP address

## Deployment Steps

### 1. Run the Deployment Script

Open PowerShell as Administrator and run:

```powershell
cd C:\Websites\NewHireApp
.\deploy_iis.ps1
```

This script will:
- Install required IIS features
- Create the application pool
- Create the IIS website
- Configure Windows Authentication
- Set up proper permissions
- Start the application

### 2. Manual IIS Configuration (Alternative)

If you prefer to configure manually:

#### Create Application Pool
1. Open IIS Manager
2. Right-click "Application Pools" → "Add Application Pool"
3. Name: `ZiebartOnboardingAppPool`
4. .NET CLR Version: **No Managed Code**
5. Managed Pipeline Mode: **Integrated**
6. Click OK

#### Configure Application Pool
1. Select the application pool
2. Click "Advanced Settings"
3. Set:
   - **Start Mode**: AlwaysRunning
   - **Identity**: ApplicationPoolIdentity

#### Create Website
1. Right-click "Sites" → "Add Website"
2. Site name: `ZiebartOnboarding`
3. Application pool: `ZiebartOnboardingAppPool`
4. Physical path: `C:\Websites\NewHireApp`
5. Binding:
   - Type: http
   - IP address: All Unassigned
   - Port: 80
   - Host name: `ziebartonboarding.com`
6. Click OK

#### Configure Authentication
1. Select the website
2. Double-click "Authentication"
3. Disable "Anonymous Authentication"
4. Enable "Windows Authentication"

### 3. DNS Configuration

Configure your DNS to point `ziebartonboarding.com` to your server's IP address:

**A Record:**
- Name: `ziebartonboarding.com` (or `@`)
- Type: A
- Value: Your server's IP address
- TTL: 3600

**Optional - WWW Record:**
- Name: `www`
- Type: A
- Value: Your server's IP address
- TTL: 3600

### 4. SSL Certificate (Recommended for Production)

For HTTPS, you'll need to:

1. Obtain an SSL certificate for `ziebartonboarding.com`
2. Install the certificate on the server
3. Add HTTPS binding in IIS:
   - Port: 443
   - SSL certificate: Your certificate
   - Host name: `ziebartonboarding.com`

4. Update `web.config` to redirect HTTP to HTTPS (optional)

### 5. Firewall Configuration

Ensure the following ports are open:
- **Port 80** (HTTP)
- **Port 443** (HTTPS, if using SSL)

### 6. Verify Deployment

1. **Check Application Pool Status:**
   - Open IIS Manager
   - Check that `ZiebartOnboardingAppPool` is "Started"

2. **Test the Application:**
   - Open browser and navigate to: `http://ziebartonboarding.com`
   - You should see the login/dashboard page

3. **Check Logs:**
   - Location: `C:\Websites\NewHireApp\logs\wfastcgi.log`
   - Check for any errors

### 7. Troubleshooting

#### Application Pool Not Starting
- Check Event Viewer for errors
- Verify Python is installed correctly
- Check that `wfastcgi.py` exists in the venv

#### 500 Internal Server Error
- Check `wfastcgi.log` for Python errors
- Verify database connection string in `config.py`
- Check Windows Authentication is enabled
- Verify file permissions on the application folder

#### Windows Authentication Not Working
- Ensure Windows Authentication is enabled in IIS
- Check that Anonymous Authentication is disabled
- Verify the user has proper domain permissions

#### Database Connection Issues
- Verify SQL Server is accessible from the server
- Check ODBC Driver 18 is installed
- Test connection string manually
- Verify firewall allows SQL Server port (42278)

### 8. Production Checklist

- [ ] SSL certificate installed and configured
- [ ] HTTPS binding added
- [ ] Secret key changed in `config.py` (use strong random key)
- [ ] Database connection string verified
- [ ] Windows Authentication working
- [ ] File uploads directory has write permissions
- [ ] Logs directory has write permissions
- [ ] DNS configured and propagated
- [ ] Firewall rules configured
- [ ] Application tested and working
- [ ] Backup strategy in place

### 9. Maintenance

**Logs Location:**
- Application logs: `C:\Websites\NewHireApp\logs\wfastcgi.log`
- IIS logs: `C:\inetpub\logs\LogFiles\W3SVC[SiteID]\`

**Restart Application:**
```powershell
Restart-WebAppPool -Name ZiebartOnboardingAppPool
```

**Stop Application:**
```powershell
Stop-WebAppPool -Name ZiebartOnboardingAppPool
```

**Start Application:**
```powershell
Start-WebAppPool -Name ZiebartOnboardingAppPool
```

## Support

For issues or questions, check:
1. IIS Event Viewer
2. Application logs: `C:\Websites\NewHireApp\logs\`
3. Windows Event Viewer → Application logs
