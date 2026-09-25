"""Lokasi file & konfigurasi dasar.

Saat dibundel PyInstaller, kode & template berada di sys._MEIPASS (read-only),
sedangkan data (database, foto, kunci) disimpan di folder `data/` di samping .exe
agar tidak hilang saat aplikasi di-update.
"""
import os
import sys

APP_NAME = "Presensi Siswa Digital"
APP_VERSION = "1.0.0"

if getattr(sys, "frozen", False):
    BUNDLE_DIR = os.path.join(sys._MEIPASS, "app")  # type: ignore[attr-defined]
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(BUNDLE_DIR)

DATA_DIR = os.environ.get("PRESENSI_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "presensi.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
FOTO_DIR = os.path.join(UPLOAD_DIR, "foto")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")
KEY_FILE = os.path.join(DATA_DIR, "secret.key")

HOST = os.environ.get("PRESENSI_HOST", "0.0.0.0")
PORT = int(os.environ.get("PRESENSI_PORT", "5000"))


def ensure_dirs():
    for d in (DATA_DIR, UPLOAD_DIR, FOTO_DIR, BACKUP_DIR):
        os.makedirs(d, exist_ok=True)
