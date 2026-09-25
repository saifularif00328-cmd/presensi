"""Akses database SQLite lokal.

- WAL + synchronous=FULL: setiap commit langsung aman di disk, tahan mati listrik.
- Satu koneksi per request (flask.g); job background memakai `connect()` sendiri.
"""
import os
import secrets
import sqlite3
from contextlib import contextmanager

from flask import current_app, g
from werkzeug.security import generate_password_hash

from . import config

DEFAULT_SETTINGS = {
    "nama_sekolah": "SMP Negeri Contoh",
    "alamat_sekolah": "Jl. Pendidikan No. 1",
    "hari_sekolah": "1,2,3,4,5",          # ISO weekday (1 = Senin ... 7 = Minggu)
    "modul_ibadah_aktif": "1",
    "monitor_refresh_detik": "3",
    "fonnte_token": "",
    "fonnte_kuota": "",
    "fonnte_kuota_cek": "",
    "wa_on_masuk": "1",
    "wa_on_pulang": "1",
    "wa_on_alpha": "1",
    "wa_on_izin": "1",
    "wa_on_pelanggaran": "1",
    "wa_tpl_masuk": "Assalamu'alaikum Bapak/Ibu, ananda *{nama_siswa}* ({kelas}) telah *absen masuk* pukul {jam} dengan status *{status}*. Terima kasih.",
    "wa_tpl_pulang": "Bapak/Ibu, ananda *{nama_siswa}* ({kelas}) telah *absen pulang* pukul {jam} ({status}). Mohon dipantau perjalanan pulangnya.",
    "wa_tpl_alpha": "Bapak/Ibu, ananda *{nama_siswa}* ({kelas}) tercatat *tidak hadir tanpa keterangan (Alpha)* hari ini. Mohon konfirmasi ke pihak sekolah.",
    "wa_tpl_izin": "Bapak/Ibu, pengajuan *{status}* untuk ananda *{nama_siswa}* ({kelas}) telah *disetujui* sekolah. {keterangan}",
    "wa_tpl_pelanggaran": "Bapak/Ibu, ananda *{nama_siswa}* ({kelas}) tercatat melakukan pelanggaran: *{status}* pada {jam}. Mohon bimbingannya di rumah.",
    "license_key": "",
    "license_status": "",
    "license_server": "",
    "license_checked": "",
    "license_last_seen": "",
    # profil sekolah (sisi belakang kartu)
    "kota_sekolah": "",
    "telepon_sekolah": "",
    "email_sekolah": "",
    "website_sekolah": "",
    "npsn": "",
    "akreditasi": "",
    "kepala_sekolah": "",
    "nip_kepala": "",
    "ttd_kepsek": "",
    "visi": "Terwujudnya peserta didik yang beriman, berakhlak mulia, berprestasi, dan peduli "
            "lingkungan.",
    "misi": "Menyelenggarakan pembelajaran yang aktif, kreatif, dan menyenangkan.\n"
            "Menanamkan nilai keimanan, kejujuran, dan kedisiplinan dalam kehidupan sehari-hari.\n"
            "Mengembangkan potensi akademik dan non-akademik peserta didik secara optimal.\n"
            "Membangun budaya sekolah yang bersih, aman, dan ramah lingkungan.",
    "kartu_ketentuan": "Kartu ini adalah identitas resmi siswa dan wajib dibawa setiap hari.\n"
                       "Kartu digunakan untuk presensi masuk dan pulang dengan memindai kode QR.\n"
                       "Kartu tidak boleh dipinjamkan, diperjualbelikan, atau disalahgunakan.\n"
                       "Kehilangan atau kerusakan kartu wajib segera dilaporkan ke Tata Usaha.\n"
                       "Bagi yang menemukan kartu ini, mohon dikembalikan ke alamat sekolah.",
    "kartu_berlaku": "Berlaku selama pemegang kartu masih berstatus siswa aktif.",
}


def connect(path=None):
    conn = sqlite3.connect(path or current_db_path(), timeout=15, detect_types=0,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    return conn


def current_db_path():
    try:
        return current_app.config["DB_PATH"]
    except RuntimeError:
        return config.DB_PATH


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def standalone(path=None):
    """Koneksi terpisah untuk thread background / scheduler."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- helpers
def query(sql, args=(), one=False, db=None):
    cur = (db or get_db()).execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=(), db=None, commit=True):
    conn = db or get_db()
    cur = conn.execute(sql, args)
    if commit:
        conn.commit()
    return cur.lastrowid


def get_setting(key, default=None, db=None):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True, db=db)
    if row is None or row["value"] is None:
        return DEFAULT_SETTINGS.get(key, default) if default is None else default
    return row["value"]


def set_setting(key, value, db=None, commit=True):
    execute("INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, "" if value is None else str(value)), db=db, commit=commit)


def new_qr_token():
    return secrets.token_hex(8).upper()


# ---------------------------------------------------------------- init
def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = connect(path)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    _seed(conn)
    conn.commit()
    conn.close()


def _seed(conn):
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    # Secret untuk checksum QR & token API cabang — dibuat sekali per instalasi
    conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('qr_secret', ?)",
                 (secrets.token_hex(16),))
    conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('cabang_api_token', ?)",
                 (secrets.token_urlsafe(18),))

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users(username, password_hash, nama, role) VALUES (?,?,?,?)",
                     ("admin", generate_password_hash("admin123"), "Administrator", "admin"))

    if conn.execute("SELECT COUNT(*) FROM aturan_jam").fetchone()[0] == 0:
        conn.execute("INSERT INTO aturan_jam(nama, jam_masuk, batas_telat, batas_pulang_cepat, "
                     "jam_pulang, jam_tutup) VALUES ('Default', '07:00', '07:15', '11:00', "
                     "'14:00', '16:00')")

    if conn.execute("SELECT COUNT(*) FROM tahun_ajaran").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO tahun_ajaran(nama, semester, tanggal_mulai, tanggal_selesai, aktif) "
            "VALUES (?,?,?,?,?)",
            [("2026/2027", "Ganjil", "2026-07-13", "2026-12-19", 1),
             ("2026/2027", "Genap", "2027-01-04", "2027-06-19", 0)])

    if conn.execute("SELECT COUNT(*) FROM tata_tertib").fetchone()[0] == 0:
        conn.executemany("INSERT INTO tata_tertib(judul, isi, urutan) VALUES (?,?,?)", [
            ("Kehadiran", "Siswa wajib hadir di sekolah paling lambat pukul 07.00 dan "
                          "melakukan scan kartu presensi saat datang dan pulang.", 1),
            ("Seragam", "Siswa wajib mengenakan seragam sesuai jadwal yang ditetapkan sekolah.", 2),
            ("Kartu Pelajar", "Kartu pelajar ber-QR wajib dibawa setiap hari. Kehilangan kartu "
                              "wajib dilaporkan ke TU.", 3),
        ])

    if conn.execute("SELECT COUNT(*) FROM jenis_pelanggaran").fetchone()[0] == 0:
        conn.executemany("INSERT INTO jenis_pelanggaran(nama, kategori, poin) VALUES (?,?,?)", [
            ("Terlambat masuk sekolah", "Ringan", 5),
            ("Tidak memakai atribut lengkap", "Ringan", 5),
            ("Membolos / keluar tanpa izin", "Sedang", 20),
            ("Merokok di lingkungan sekolah", "Berat", 50),
            ("Berkelahi", "Berat", 75),
        ])
