@echo off
REM Server aktivasi lisensi (khusus vendor)
REM   Halaman admin : http://localhost:8501  (hanya laptop ini)
REM   API sekolah   : port 8500               (dibuka ke internet via ngrok / Cloudflare Tunnel)
cd /d "%~dp0"
if not exist venv (
  python -m venv venv
  venv\Scripts\python -m pip install -r requirements.txt waitress
)
if not exist vendor\private_key.pem venv\Scripts\python tools\vendor_init.py
REM Tunnel otomatis: ngrok (bila vendor\ngrok_domain.txt ada) atau Cloudflare (bila config.yml ada)
if exist vendor\ngrok_domain.txt (
  set /p NGROK_DOMAIN=<vendor\ngrok_domain.txt
  goto ngrok
)
where cloudflared >nul 2>nul && if exist "%USERPROFILE%\.cloudflared\config.yml" start "Cloudflare Tunnel" cloudflared tunnel run
goto server
:ngrok
where ngrok >nul 2>nul && start "ngrok" cmd /k ngrok http --url=%NGROK_DOMAIN% 8500
where ngrok >nul 2>nul || echo PERINGATAN: ngrok tidak ditemukan. Lihat license_server\TUTORIAL_NGROK.md
:server
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8501"
venv\Scripts\python license_server\server.py
pause
