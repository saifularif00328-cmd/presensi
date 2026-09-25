@echo off
REM Build aplikasi Windows standalone (.exe)
REM Ganti VENDOR_SECRET di app\license.py sebelum build (harus sama dengan tools\keygen.py).
python -m pip install -r requirements.txt pyinstaller waitress
pyinstaller --noconfirm presensi.spec
echo.
echo Selesai: dist\PresensiSiswa\PresensiSiswa.exe
pause
