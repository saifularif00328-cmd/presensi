"""Utilitas waktu, kalender sekolah, dan enkripsi."""
import os
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken

from . import config
from .db import get_setting, query

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
         "September", "Oktober", "November", "Desember"]
KETERANGAN = {"H": "Hadir", "I": "Izin", "S": "Sakit", "A": "Alpha", "D": "Dispensasi"}


# ------------------------------------------------------------------ waktu
def now():
    """Satu-satunya sumber waktu aplikasi (mudah di-mock saat pengujian)."""
    return datetime.now()


def today():
    return now().date()


def today_str():
    return today().isoformat()


def hhmm(t=None):
    return (t or now()).strftime("%H:%M:%S")


def parse_date(s, default=None):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def tanggal_indo(d):
    if isinstance(d, str):
        d = parse_date(d)
    if not d:
        return "-"
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]} {d.year}"


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ------------------------------------------------------------------ kalender
def hari_sekolah(db=None):
    raw = get_setting("hari_sekolah", db=db) or "1,2,3,4,5"
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


def libur_on(d, db=None):
    row = query("SELECT keterangan FROM libur WHERE tanggal = ?", (d.isoformat(),),
                one=True, db=db)
    return row["keterangan"] if row else None


def is_school_day(d, db=None):
    """Hari efektif = hari sekolah dan bukan tanggal libur."""
    if d.isoweekday() not in hari_sekolah(db):
        return False
    return libur_on(d, db) is None


def school_days(start, end, db=None):
    hs = hari_sekolah(db)
    libur = {r["tanggal"] for r in query(
        "SELECT tanggal FROM libur WHERE tanggal BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()), db=db)}
    return [d for d in daterange(start, end)
            if d.isoweekday() in hs and d.isoformat() not in libur]


# ------------------------------------------------------------------ enkripsi
def _fernet():
    config.ensure_dirs()
    if not os.path.exists(config.KEY_FILE):
        with open(config.KEY_FILE, "wb") as f:
            f.write(Fernet.generate_key())
    with open(config.KEY_FILE, "rb") as f:
        return Fernet(f.read().strip())


def encrypt(text):
    if not text:
        return ""
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def normalize_wa(nomor):
    """08xx / +628xx / 628xx → 628xx. Mengembalikan '' bila tidak valid."""
    if not nomor:
        return ""
    n = "".join(ch for ch in str(nomor) if ch.isdigit())
    if n.startswith("0"):
        n = "62" + n[1:]
    elif n.startswith("8"):
        n = "62" + n
    return n if len(n) >= 10 else ""
