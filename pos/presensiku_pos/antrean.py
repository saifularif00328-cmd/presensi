"""Antrean scan lokal (SQLite) — scan tetap tersimpan saat internet putus atau PC dimatikan."""
import json
import sqlite3
import threading
import time


class Antrean:
    def __init__(self, path):
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS scan (uuid TEXT PRIMARY KEY, kode TEXT NOT NULL, "
                        "kunci TEXT NOT NULL, ts INTEGER NOT NULL, dibuat REAL NOT NULL, "
                        "terkirim INTEGER NOT NULL DEFAULT 0, hasil TEXT, percobaan INTEGER DEFAULT 0)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_scan_belum ON scan(terkirim, dibuat)")

    def tambah(self, uuid, kode, kunci, ts):
        with self._lock:
            self.db.execute("INSERT OR IGNORE INTO scan(uuid, kode, kunci, ts, dibuat) VALUES (?,?,?,?,?)",
                            (uuid, kode, kunci, int(ts), time.time()))

    def belum(self, batas=50):
        with self._lock:
            rows = self.db.execute("SELECT uuid, kode, kunci, ts FROM scan WHERE terkirim = 0 "
                                   "ORDER BY dibuat LIMIT ?", (batas,)).fetchall()
        return [{"uuid": u, "kode": k, "kunci": c, "ts": t} for u, k, c, t in rows]

    def tandai(self, uuid, hasil):
        with self._lock:
            self.db.execute("UPDATE scan SET terkirim = 1, hasil = ? WHERE uuid = ?",
                            (json.dumps(hasil), uuid))

    def gagal(self, uuid):
        with self._lock:
            self.db.execute("UPDATE scan SET percobaan = percobaan + 1 WHERE uuid = ?", (uuid,))

    def jumlah_belum(self):
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM scan WHERE terkirim = 0").fetchone()[0]

    def bersihkan(self, hari=7):
        with self._lock:
            self.db.execute("DELETE FROM scan WHERE terkirim = 1 AND dibuat < ?",
                            (time.time() - hari * 86400,))
