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
REM Paket opsional untuk scan via webcam PC (OpenCV + pyzbar). Gagal pun aplikasi tetap jalan.
venv\Scripts\python -c "import cv2, pyzbar.pyzbar" >nul 2>nul || (
  echo Memasang paket webcam ^(opencv-python, pyzbar^)...
  venv\Scripts\python -m pip install opencv-python pyzbar
)
venv\Scripts\python run.py --open
pause
