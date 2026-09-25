@echo off
REM Server aktivasi lisensi (khusus vendor) - http://localhost:8500
cd /d "%~dp0"
if not exist venv (
  python -m venv venv
  venv\Scripts\python -m pip install -r requirements.txt waitress
)
if not exist vendor\private_key.pem venv\Scripts\python tools\vendor_init.py
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8500"
venv\Scripts\python license_server\server.py
pause
