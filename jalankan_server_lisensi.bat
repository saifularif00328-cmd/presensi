@echo off
REM Server aktivasi lisensi (khusus vendor) - admin: http://localhost:8500
cd /d "%~dp0"
if not exist venv (
  python -m venv venv
  venv\Scripts\python -m pip install -r requirements.txt waitress
)
if not exist vendor\private_key.pem venv\Scripts\python tools\vendor_init.py
REM Nyalakan Cloudflare Tunnel otomatis bila sudah disiapkan (lihat license_server\TUTORIAL_CLOUDFLARE.md)
where cloudflared >nul 2>nul && if exist "%USERPROFILE%\.cloudflared\config.yml" start "Cloudflare Tunnel" cloudflared tunnel run
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8500"
venv\Scripts\python license_server\server.py
pause
