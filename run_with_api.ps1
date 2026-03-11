# Run the app locally with Data API connections for testing.
# Terminal 1: Start the Data API (holds DB connection).
# Terminal 2: Start the Flask app with API_BASE_URL set.

$ErrorActionPreference = "Stop"
$ApiPort = 8002
$ApiUrl = "http://localhost:$ApiPort"

Write-Host "=== NewHireApp: run with Data API ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option A - Two terminals:" -ForegroundColor Yellow
Write-Host "  1. Terminal 1 (Data API):  .\venv\Scripts\Activate.ps1; python -m uvicorn data_api.main:app --host 127.0.0.1 --port $ApiPort"
Write-Host "  2. Terminal 2 (Flask app): .\venv\Scripts\Activate.ps1; `$env:API_BASE_URL = `"$ApiUrl`"; python app.py"
Write-Host ""
Write-Host "Option B - Start Data API in background, then Flask in foreground:" -ForegroundColor Yellow
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  Start-Process python -ArgumentList `"-m`",`"uvicorn`",`"data_api.main:app`",`"--host`",`"127.0.0.1`",`"--port`",`"$ApiPort`" -WindowStyle Hidden"
Write-Host "  Start-Sleep -Seconds 2"
Write-Host "  `$env:API_BASE_URL = `"$ApiUrl`"; python app.py"
Write-Host ""
Write-Host "Flask will be at http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "Data API will be at $ApiUrl (e.g. $ApiUrl/health)" -ForegroundColor Green
