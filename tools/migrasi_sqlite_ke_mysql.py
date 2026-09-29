"""Pindahkan data dari versi lama (SQLite: data/presensi.db) ke MySQL/MariaDB.

    python tools/migrasi_sqlite_ke_mysql.py                     # pakai data/presensi.db & data/config.ini
    python tools/migrasi_sqlite_ke_mysql.py --sqlite D:\\lama\\presensi.db --timpa

Database MySQL tujuan diambil dari data/config.ini atau env PRESENSI_DB_URL (lihat app/config.py).
Foto/logo di data/uploads tidak perlu dipindah bila folder data yang sama dipakai.
Aman diulang dengan --timpa (tabel tujuan dikosongkan dulu).
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config  # noqa: E402
from app.db import connect, init_db  # noqa: E402

# Urutan mengikuti foreign key (induk dulu)
TABEL = ["settings", "tahun_ajaran", "guru", "kelas", "siswa", "users", "aturan_jam", "presensi",
         "scan_log", "tutup_harian", "izin", "izin_keluar", "pengajuan_kartu", "ibadah",
         "presensi_ibadah", "tata_tertib", "jenis_pelanggaran", "pelanggaran", "libur", "info",
         "cabang", "notif_queue"]
GANTI_KOLOM = {"settings": {"key": "kunci", "value": "nilai"}}


def _kolom_tujuan(db, tabel):
    return {r["COLUMN_NAME"]: r["DATA_TYPE"] for r in db.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?", (tabel,)).fetchall()}


def migrasi(sqlite_path, cfg=None, timpa=False, log=print):
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(sqlite_path)
    init_db(cfg)
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    db = connect(cfg)
    hasil = {}
    try:
        db.execute("SET FOREIGN_KEY_CHECKS = 0")
        ada = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in TABEL:
            if t not in ada:
                continue
            tujuan = _kolom_tujuan(db, t)
            ganti = GANTI_KOLOM.get(t, {})
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
            if timpa or t == "settings":
                # settings selalu ditimpa agar nilai sekolah lama menggantikan nilai bawaan
                db.execute(f"DELETE FROM `{t}`")
            elif db.execute(f"SELECT COUNT(*) AS n FROM `{t}`").fetchone()["n"] and t not in (
                    "aturan_jam", "tahun_ajaran", "tata_tertib", "jenis_pelanggaran", "users"):
                raise RuntimeError(f"Tabel {t} di MySQL sudah berisi data. Pakai --timpa.")
            else:
                db.execute(f"DELETE FROM `{t}`")  # isi bawaan (seed) diganti data sekolah
            if not rows:
                hasil[t] = 0
                continue
            src_cols = [c for c in rows[0].keys() if ganti.get(c, c) in tujuan]
            dst_cols = [ganti.get(c, c) for c in src_cols]
            sql = (f"INSERT INTO `{t}` ({', '.join('`%s`' % c for c in dst_cols)}) "
                   f"VALUES ({', '.join('?' for _ in dst_cols)})")
            data = []
            for r in rows:
                vals = []
                for c, d in zip(src_cols, dst_cols):
                    v = r[c]
                    # SQLite menerima string kosong untuk tanggal; MySQL tidak
                    if v == "" and tujuan[d] in ("date", "datetime", "timestamp", "int",
                                                 "tinyint"):
                        v = None
                    vals.append(v)
                data.append(vals)
            db.executemany(sql, data)
            hasil[t] = len(rows)
            log(f"  {t:<18} {len(rows):>6} baris")
        db.execute("SET FOREIGN_KEY_CHECKS = 1")
        db.commit()
    finally:
        db.close()
        src.close()
    return hasil


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--sqlite", default=os.path.join(config.DATA_DIR, "presensi.db"),
                    help="lokasi database lama (default: data/presensi.db)")
    ap.add_argument("--timpa", action="store_true", help="kosongkan tabel tujuan sebelum impor")
    a = ap.parse_args()
    cfg = config.database()
    print(f"Sumber : {a.sqlite}")
    print(f"Tujuan : mysql://{cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}")
    hasil = migrasi(a.sqlite, cfg, timpa=a.timpa)
    print(f"Selesai: {sum(hasil.values())} baris dari {len(hasil)} tabel dipindahkan.")
    print("Simpan file presensi.db lama sebagai cadangan; aplikasi kini memakai MySQL.")


if __name__ == "__main__":
    main()
