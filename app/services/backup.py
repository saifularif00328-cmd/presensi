"""Backup & pemulihan satu sekolah dalam satu file ZIP.

Isi ZIP:
- database.sql  : dump seluruh tabel (CREATE TABLE + INSERT), tanpa perlu program mysqldump
- uploads/...   : foto siswa, logo, tanda tangan, lampiran
- keys/...      : kunci enkripsi (token Fonnte) & kunci sesi — agar data terenkripsi tetap terbaca
- meta.json     : versi aplikasi, nama sekolah, waktu backup

Dipakai oleh: backup harian (scheduler), tombol Backup, dan perintah pindah server ke VPS.
"""
import io
import json
import os
import zipfile

from .. import config, utils
from ..db import connect, get_setting, split_sql

KEY_FILES = ("secret.key", "flask.key")


def _tables(db):
    return [r["TABLE_NAME"] for r in db.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME").fetchall()]


def dump_sql(db):
    """Dump SQL lengkap (string). Urutan tabel bebas karena FOREIGN_KEY_CHECKS dimatikan."""
    raw = db.raw
    out = ["-- Presensi Siswa Digital: dump database",
           "SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS = 0;"]
    for t in _tables(db):
        create = db.execute(f"SHOW CREATE TABLE `{t}`").fetchone()["Create Table"]
        out += [f"DROP TABLE IF EXISTS `{t}`;", create + ";"]
        rows = db.execute(f"SELECT * FROM `{t}`").fetchall()
        for i in range(0, len(rows), 200):
            chunk = rows[i:i + 200]
            cols = ", ".join(f"`{c}`" for c in chunk[0].keys())
            vals = ",\n".join("(" + ", ".join(raw.escape(v) for v in r.values()) + ")"
                              for r in chunk)
            out.append(f"INSERT INTO `{t}` ({cols}) VALUES\n{vals};")
    out.append("SET FOREIGN_KEY_CHECKS = 1;")
    return "\n".join(out) + "\n"


def load_sql(db, sql):
    """Jalankan dump SQL ke database (menimpa tabel yang ada)."""
    cur = db.raw.cursor()
    for stmt in split_sql(sql):
        cur.execute(stmt)
    db.commit()


def make_zip(db):
    """Buat backup ZIP di memori (bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("database.sql", dump_sql(db))
        if os.path.isdir(config.UPLOAD_DIR):
            for root, _dirs, files in os.walk(config.UPLOAD_DIR):
                for f in files:
                    full = os.path.join(root, f)
                    z.write(full, "uploads/" + os.path.relpath(full, config.UPLOAD_DIR)
                            .replace(os.sep, "/"))
        for k in KEY_FILES:
            p = os.path.join(config.DATA_DIR, k)
            if os.path.exists(p):
                z.write(p, "keys/" + k)
        z.writestr("meta.json", json.dumps({
            "app": config.APP_NAME, "versi": config.APP_VERSION,
            "sekolah": get_setting("nama_sekolah", db=db),
            "waktu": utils.now().strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=1))
    return buf.getvalue()


def restore_zip(data, cfg=None, data_dir=None):
    """Pulihkan backup ZIP ke database `cfg` dan folder data `data_dir`. Mengembalikan meta."""
    data_dir = data_dir or config.DATA_DIR
    with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as z:
        names = z.namelist()
        if "database.sql" not in names:
            raise ValueError("File bukan backup Presensi (database.sql tidak ada)")
        meta = json.loads(z.read("meta.json")) if "meta.json" in names else {}
        db = connect(cfg)
        try:
            load_sql(db, z.read("database.sql").decode("utf-8"))
        finally:
            db.close()
        upload_dir = os.path.join(data_dir, "uploads")
        for n in names:
            if n.endswith("/"):
                continue
            if n.startswith("uploads/"):
                dest = os.path.normpath(os.path.join(upload_dir, n[len("uploads/"):]))
            elif n.startswith("keys/") and os.path.basename(n) in KEY_FILES:
                dest = os.path.join(data_dir, os.path.basename(n))
            else:
                continue
            if not dest.startswith(os.path.normpath(data_dir) + os.sep):
                continue  # cegah path traversal (../)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(z.read(n))
    return meta


def backup_harian(db, simpan=14):
    """Simpan backup ZIP ke data/backup/presensi-YYYY-MM-DD.zip (simpan N terakhir)."""
    config.ensure_dirs()
    dest = os.path.join(config.BACKUP_DIR, f"presensi-{utils.today_str()}.zip")
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(make_zip(db))
    os.replace(tmp, dest)
    files = sorted(f for f in os.listdir(config.BACKUP_DIR)
                   if f.startswith("presensi-") and f.endswith(".zip"))
    for old in files[:-simpan]:
        os.remove(os.path.join(config.BACKUP_DIR, old))
    return dest
