@echo off
REM Build aplikasi Windows standalone (.exe) untuk dibagikan ke sekolah.
REM Sebelum build: 1) python tools\vendor_init.py  (membuat app\license_public.pem)
REM                2) isi DEFAULT_SERVER_URL di app\license.py dengan alamat server lisensi Anda
cd /d "%~dp0"
echo Folder aplikasi: %CD%
if not exist app\license_public.pem (
  echo GAGAL: app\license_public.pem belum ada.
  echo Jalankan dulu: venv\Scripts\python tools\vendor_init.py
  pause
  exit /b 1
)
if not exist venv (
  python -m venv venv
)
venv\Scripts\python -m pip install -r requirements.txt pyinstaller waitress
if errorlevel 1 goto gagal
venv\Scripts\python -c "from app.license import DEFAULT_SERVER_URL as u; print(); print('Alamat server lisensi bawaan:', u or '(KOSONG - sekolah harus mengetik alamat server sendiri)'); print()"
venv\Scripts\python -m PyInstaller --noconfirm presensi.spec
if errorlevel 1 goto gagal
if not exist "dist\PresensiSiswa\PresensiSiswa.exe" goto gagal
echo.
echo ============================================================
echo  BERHASIL. Hasil build:
echo  %CD%\dist\PresensiSiswa
echo  Bagikan SELURUH isi folder itu (PresensiSiswa.exe + _internal).
echo ============================================================
explorer "%CD%\dist\PresensiSiswa"
pause
exit /b 0
:gagal
echo.
echo ============================================================
echo  BUILD GAGAL. Gulir ke atas dan screenshot pesan error
echo  (baris berwarna merah / berisi "Error").
echo ============================================================
pause
exit /b 1
