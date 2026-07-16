# Python IIS Web Application

A Python web application configured to run on IIS using FastCGI, wfastcgi, and URL Rewrite.

## Prerequisites

1. **Python 3.7+** installed on Windows
2. **IIS** (Internet Information Services) enabled on Windows
3. **FastCGI Module** - Built into IIS (usually enabled by default)
4. **URL Rewrite Module** - Download from [Microsoft](https://www.iis.net/downloads/microsoft/url-rewrite)
5. **wfastcgi** - Python package for FastCGI support

## Installation Steps

### 1. Install Python Dependencies

```powershell
# Create virtual environment (recommended)
python -m venv venv
.\venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 2. Enable IIS Features

Open PowerShell as Administrator and run:

```powershell
# Enable IIS
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServer
Enable-WindowsOptionalFeature -Online -FeatureName IIS-CommonHttpFeatures
Enable-WindowsOptionalFeature -Online -FeatureName IIS-HttpErrors
Enable-WindowsOptionalFeature -Online -FeatureName IIS-ApplicationInit
Enable-WindowsOptionalFeature -Online -FeatureName IIS-CGI

# Enable FastCGI (usually included with IIS)
Enable-WindowsOptionalFeature -Online -FeatureName IIS-CGI
```

### 3. Install URL Rewrite Module

1. Download URL Rewrite Module 2.1 from: https://www.iis.net/downloads/microsoft/url-rewrite
2. Install the downloaded `.msi` file
3. Restart IIS after installation

### 4. Configure wfastcgi

```powershell
# Activate virtual environment if using one
.\venv\Scripts\activate

# Install wfastcgi
pip install wfastcgi

# Enable wfastcgi (run as Administrator)
wfastcgi-enable
```

This will output something like:
```
Python 3.9.0 (C:\Python39\python.exe) | C:\Python39\Lib\site-packages\wfastcgi.py
```

**Note the paths** - you'll need to update `web.config` with your actual Python path.

### 5. Update web.config

Edit `web.config` and update the following paths to match your system:

- **Python executable path**: Update `C:\Python39\python.exe` to your Python path
- **wfastcgi.py path**: Update `C:\Python39\Lib\site-packages\wfastcgi.py` to your wfastcgi location
- **Application path**: Update `C:\Websites\NewHireApp` to your actual application directory
- **Virtual environment**: If using a venv, update paths to point to `venv\Scripts\python.exe` and `venv\Lib\site-packages\wfastcgi.py`

### 6. Create Logs Directory

```powershell
mkdir logs
```

### 7. Configure IIS Application

1. Open **IIS Manager** (inetmgr)
2. Right-click **Default Web Site** (or create a new site)
3. Select **Add Application**
4. Set:
   - **Alias**: `NewHireApp` (or your preferred name)
   - **Application pool**: Create new or use existing
   - **Physical path**: `C:\Websites\NewHireApp` (your app directory)
5. Click **OK**

### 8. Set Application Pool Identity

1. In IIS Manager, select **Application Pools**
2. Select your application pool
3. Click **Advanced Settings**
4. Set **Identity** to an account with appropriate permissions (or use ApplicationPoolIdentity)

### 9. Set Folder Permissions

Grant the application pool identity read/execute permissions on your application folder:

```powershell
icacls "C:\Websites\NewHireApp" /grant "IIS AppPool\DefaultAppPool:(OI)(CI)RX" /T
```

### 10. Test the Application

1. Open a browser and navigate to: `http://localhost/NewHireApp`
2. You should see the home page
3. Test API endpoints:
   - `http://localhost/NewHireApp/api/health`
   - `http://localhost/NewHireApp/api/info`

## Troubleshooting

### Check wfastcgi Installation

```powershell
wfastcgi-disable  # Disable if needed
wfastcgi-enable   # Re-enable
```

### View Logs

Check the log file specified in `web.config`:
- Default: `C:\Websites\NewHireApp\logs\wfastcgi.log`

### Common Issues

1. **500 Internal Server Error**
   - Check Python path in `web.config`
   - Verify wfastcgi is installed and enabled
   - Check folder permissions
   - Review IIS logs: `C:\inetpub\logs\LogFiles`

2. **Module Not Found Errors**
   - Ensure virtual environment is activated when installing packages
   - Update `PYTHONPATH` in `web.config` to include your app directory

3. **FastCGI Errors**
   - Verify FastCGI module is enabled in IIS
   - Check `web.config` FastCGI configuration
   - Restart IIS: `iisreset`

## Application Structure

```
ziebartonboardingapp/
├── app.py                 # Flask entry (WSGI: app.application)
├── config.py              # Env / MSSQL / feature flags
├── blueprints/            # HTTP routes
├── services/              # Domain logic (PDF, mail, CSRF, jobs, …)
├── db/migrations_runtime.py
├── templates/
├── web.config             # IIS FastCGI + rewrite (uploads via Flask)
├── requirements.txt
└── logs/
```

## Health check

- `GET /healthz` — JSON `{app, db, uploads}` (use for IIS/load balancer probes)

## Security notes (production)

- Set a unique `SECRET_KEY` in `.env` (app refuses the insecure default).
- CSRF is enabled (Flask-WTF); forms and `fetch` get tokens automatically.
- Only `static/` is served by IIS as files; `uploads/` goes through Flask auth.
- Document signing today is **visual overlay + audit log**. Cryptographic PAdES signing is not configured (needs HSM/KMS certs).
- Optional admin Test Form Wizard is off unless `ENABLE_TEST_FORM_WIZARD=true`.
- Optional `data_api/` service requires `DATA_API_KEY` (refuses to serve without it).

## Development

```powershell
# Set ALLOW_INSECURE_SECRET_KEY=1 only for local throwaway use, or use a real SECRET_KEY
$env:FLASK_DEBUG="1"
python app.py
```

The app runs on `http://localhost:5000` (debug only when `FLASK_DEBUG=1`).

## Notes

- Update `web.config` paths for your IIS install
- Prefer `.env` for secrets (blocked from HTTP by IIS hiddenSegments)
- See `ENV_VARS_REFERENCE.md` for all environment variables

