"""Akses database MySQL / MariaDB.

- Satu koneksi per request (flask.g); job background memakai `connect()` sendiri.
- Kode aplikasi tetap menulis SQL dengan placeholder `?`; diterjemahkan ke `%s` di sini.
- Tabel InnoDB (transaksi + foreign key), karakter utf8mb4.
"""
import os
import secrets
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

import pymysql
import pymysql.converters
import pymysql.cursors
from pymysql.constants import FIELD_TYPE
from pymysql.err import IntegrityError  # noqa: F401  (dipakai blueprint: from ..db import IntegrityError)

from flask import current_app, g
from werkzeug.security import generate_password_hash

from . import config

DEFAULT_SETTINGS = {
    "nama_sekolah": "SMP Negeri Contoh",
    "alamat_sekolah": "Jl. Pendidikan No. 1",
    "zona_waktu": "Asia/Jakarta",         # Asia/Jakarta (WIB) / Asia/Makassar (WITA) / Asia/Jayapura (WIT)
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


class Row(dict):
    """Baris hasil query: bisa diakses dengan nama kolom (row["nama"]) maupun indeks (row[0])."""

    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return dict.__getitem__(self, k)


def _decimal(b):
    d = Decimal(b.decode() if isinstance(b, bytes) else b)
    return int(d) if d == d.to_integral_value() else float(d)


# Tanggal/jam dikembalikan sebagai teks ("YYYY-MM-DD", "YYYY-MM-DD HH:MM:SS") seperti versi SQLite,
# sehingga kode & template yang memotong string tanggal tetap berjalan. SUM()/AVG() (DECIMAL)
# dikembalikan sebagai int/float agar bisa langsung dihitung.
_CONV = dict(pymysql.converters.conversions)
for _t in (FIELD_TYPE.DATE, FIELD_TYPE.DATETIME, FIELD_TYPE.TIMESTAMP, FIELD_TYPE.TIME):
    _CONV.pop(_t, None)
_CONV[FIELD_TYPE.NEWDECIMAL] = _decimal
_CONV[FIELD_TYPE.DECIMAL] = _decimal


def _translate(sql):
    """Placeholder gaya SQLite (?) -> gaya PyMySQL (%s); % literal di-escape."""
    out, quote = [], None
    for ch in sql:
        if quote:
            out.append("%%" if ch == "%" else ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
        elif ch == "?":
            out.append("%s")
        elif ch == "%":
            out.append("%%")
        else:
            out.append(ch)
    return "".join(out)


class Cursor:
    def __init__(self, cur):
        self._cur = cur

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        r = self._cur.fetchone()
        return Row(r) if r is not None else None

    def fetchall(self):
        return [Row(r) for r in self._cur.fetchall()]

    def close(self):
        self._cur.close()


class Connection:
    """Pembungkus tipis PyMySQL dengan antarmuka mirip sqlite3 (execute/executemany/commit)."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, args=()):
        cur = self.raw.cursor()
        cur.execute(_translate(sql), tuple(args))
        return Cursor(cur)

    def executemany(self, sql, seq):
        cur = self.raw.cursor()
        cur.executemany(_translate(sql), [tuple(a) for a in seq])
        return Cursor(cur)

    def executescript(self, script):
        for stmt in split_sql(script):
            self.raw.cursor().execute(stmt)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        try:
            self.raw.close()
        except pymysql.Error:
            pass


def split_sql(script):
    """Pisahkan skrip SQL per pernyataan (abaikan komentar `--` dan titik koma di dalam string)."""
    stmts, buf, quote = [], [], None
    i = 0
    while i < len(script):
        ch = script[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(script):
                buf.append(script[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch == "-" and script.startswith("--", i):
            j = script.find("\n", i)
            i = len(script) if j < 0 else j
            continue
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        stmts.append(stmt)
    return stmts


def db_config():
    try:
        return current_app.config["DATABASE"]
    except (RuntimeError, KeyError):
        return config.database()


def raw_connect(cfg=None, database=True):
    cfg = dict(cfg or db_config())
    return pymysql.connect(
        host=cfg.get("host", "127.0.0.1"), port=int(cfg.get("port", 3306)),
        user=cfg.get("user", "root"), password=cfg.get("password", ""),
        database=cfg.get("database") if database else None,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, conv=_CONV,
        autocommit=False, connect_timeout=10,
        init_command="SET time_zone = '%s', sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'"
                     % tz_offset())


def tz_offset():
    """Offset zona waktu sekolah (mis. +07:00) untuk NOW()/CURRENT_TIMESTAMP di MySQL."""
    from .utils import zona_cached
    raw = datetime.now(zona_cached()).strftime("%z")  # +0700
    return raw[:3] + ":" + raw[3:]


def connect(cfg=None):
    return Connection(raw_connect(cfg))


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def standalone(cfg=None):
    """Koneksi terpisah untuk thread background / scheduler."""
    conn = connect(cfg)
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
    row = query("SELECT nilai FROM settings WHERE kunci = ?", (key,), one=True, db=db)
    if row is None or row["nilai"] is None:
        return DEFAULT_SETTINGS.get(key, default) if default is None else default
    return row["nilai"]


def set_setting(key, value, db=None, commit=True):
    execute("INSERT INTO settings(kunci, nilai) VALUES(?, ?) "
            "ON DUPLICATE KEY UPDATE nilai = VALUES(nilai)",
            (key, "" if value is None else str(value)), db=db, commit=commit)
    if key == "zona_waktu":
        from .utils import reset_zona
        reset_zona()


def new_qr_token():
    return secrets.token_hex(8).upper()


# ---------------------------------------------------------------- init
def ensure_database(cfg=None):
    """Buat database bila belum ada (butuh hak CREATE pada user MySQL)."""
    cfg = dict(cfg or db_config())
    raw = raw_connect(cfg, database=False)
    try:
        with raw.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci" % cfg["database"].replace("`", ""))
        raw.commit()
    finally:
        raw.close()


def init_db(cfg=None):
    ensure_database(cfg)
    conn = connect(cfg)
    try:
        with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
            conn.executescript(f.read())
        migrate(conn)
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _columns(conn, table):
    return {r["COLUMN_NAME"] for r in conn.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?", (table,)).fetchall()}


def migrate(conn):
    """Perubahan skema untuk database yang dibuat versi sebelumnya (idempoten).
    Tambahkan ALTER TABLE di sini, cek dulu dengan _columns(conn, tabel)."""


def _seed(conn):
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT IGNORE INTO settings(kunci, nilai) VALUES (?, ?)", (k, v))
    # Secret untuk checksum QR & token API cabang — dibuat sekali per instalasi
    conn.execute("INSERT IGNORE INTO settings(kunci, nilai) VALUES ('qr_secret', ?)",
                 (secrets.token_hex(16),))
    conn.execute("INSERT IGNORE INTO settings(kunci, nilai) VALUES ('cabang_api_token', ?)",
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
