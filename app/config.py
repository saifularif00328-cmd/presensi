"""Lokasi file & konfigurasi dasar.

Saat dibundel PyInstaller, kode & template berada di sys._MEIPASS (read-only),
sedangkan data (database, foto, kunci) disimpan di folder `data/` di samping .exe
agar tidak hilang saat aplikasi di-update.
"""
import configparser
import os
import sys
from urllib.parse import unquote, urlparse

APP_NAME = "Presensi Siswa Digital"
APP_VERSION = "1.0.0"

if getattr(sys, "frozen", False):
    BUNDLE_DIR = os.path.join(sys._MEIPASS, "app")  # type: ignore[attr-defined]
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(BUNDLE_DIR)

DATA_DIR = os.environ.get("PRESENSI_DATA_DIR", os.path.join(BASE_DIR, "data"))
CONFIG_FILE = os.path.join(DATA_DIR, "config.ini")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
FOTO_DIR = os.path.join(UPLOAD_DIR, "foto")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")
KEY_FILE = os.path.join(DATA_DIR, "secret.key")

HOST = os.environ.get("PRESENSI_HOST", "0.0.0.0")
PORT = int(os.environ.get("PRESENSI_PORT", "5000"))


def database():
    """Koneksi MySQL/MariaDB, urutan prioritas:
    1. env PRESENSI_DB_URL, mis. mysql://presensi:rahasia@127.0.0.1:3306/presensi
    2. data/config.ini bagian [database] (host, port, user, password, database)
    3. bawaan: presensi@127.0.0.1:3306/presensi tanpa password
    """
    cfg = {"host": "127.0.0.1", "port": 3306, "user": "presensi", "password": "",
           "database": "presensi"}
    if os.path.exists(CONFIG_FILE):
        cp = configparser.ConfigParser()
        cp.read(CONFIG_FILE, encoding="utf-8")
        if cp.has_section("database"):
            cfg.update({k: v for k, v in cp.items("database") if k in cfg})
    url = os.environ.get("PRESENSI_DB_URL")
    if url:
        u = urlparse(url)
        cfg.update(host=u.hostname or cfg["host"], port=u.port or 3306,
                   user=unquote(u.username or cfg["user"]),
                   password=unquote(u.password or ""), database=u.path.lstrip("/") or "presensi")
    cfg["port"] = int(cfg["port"])
    return cfg


def ensure_dirs():
    for d in (DATA_DIR, UPLOAD_DIR, FOTO_DIR, BACKUP_DIR):
        os.makedirs(d, exist_ok=True)
