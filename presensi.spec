# PyInstaller spec — build: pyinstaller presensi.spec  (atau jalankan build_exe.bat)
# Hasil: dist/PresensiSiswa/PresensiSiswa.exe ; data tersimpan di dist/PresensiSiswa/data/
import os

block_cipher = None
_pub = [("app/license_public.pem", "app")] if os.path.exists("app/license_public.pem") else []

a = Analysis(
    ["run.py"],
    pathex=[],
    datas=[("app/templates", "app/templates"), ("app/static", "app/static"),
           ("app/schema.sql", "app"), ("app/fonts", "app/fonts")] + _pub,
    hiddenimports=["apscheduler.triggers.interval", "apscheduler.triggers.cron",
                   "apscheduler.executors.pool", "apscheduler.jobstores.memory"],
    excludes=["tkinter", "pytest"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PresensiSiswa", console=True)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="PresensiSiswa")
