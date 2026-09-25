@echo off
REM Jalankan Presensi Siswa Digital (klik 2x file ini)
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python belum terpasang. Unduh di https://www.python.org/downloads/ dan centang "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist venv (
  echo Menyiapkan lingkungan Python pertama kali, mohon tunggu...
  python -m venv venv
  venv\Scripts\python -m pip install --upgrade pip
  venv\Scripts\python -m pip install -r requirements.txt waitress
)
venv\Scripts\python run.py --open
pause
