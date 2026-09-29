"""Kartu RFID (MIFARE 13,56 MHz).

UID kartu dibaca berbeda-beda oleh tiap alat:
- ESP32 + RC522  : hex sesuai urutan byte, mis. "A1B2C3D4"
- reader USB     : sering angka desimal 10 digit (UID dibaca big-endian atau little-endian),
                   kadang hex dengan pemisah ("A1:B2:C3:D4")
Karena itu UID disimpan dalam bentuk hex (UPPERCASE) dan saat dicari dicocokkan dengan
beberapa kemungkinan urutan byte, sehingga satu kartu yang didaftarkan lewat reader USB tetap
dikenali saat di-tap di ESP32 dan sebaliknya.
"""
import re

from . import utils
from .db import execute, query

_HEX = re.compile(r"^[0-9A-F]+$")


def _bersih(text):
    return re.sub(r"[\s:\-_.]", "", (text or "").strip()).upper()


def looks_like_uid(text):
    t = _bersih(text)
    if t.isdigit():
        return 6 <= len(t) <= 20
    return bool(_HEX.match(t)) and len(t) % 2 == 0 and 8 <= len(t) <= 20


def _bytes(text):
    t = _bersih(text)
    if not looks_like_uid(text):
        return None
    if t.isdigit():
        n = int(t)
        return n.to_bytes(max(4, (n.bit_length() + 7) // 8), "big")
    return bytes.fromhex(t)


def normalize(text):
    """Bentuk simpan UID (hex uppercase), None bila bukan UID yang valid."""
    b = _bytes(text)
    return b.hex().upper() if b else None


def candidates(text):
    """Semua bentuk UID yang mungkin untuk satu hasil baca (urutan byte normal & terbalik)."""
    b = _bytes(text)
    if not b:
        return []
    return list(dict.fromkeys([b.hex().upper(), b[::-1].hex().upper()]))


def find_by_uid(text, db=None):
    """(siswa, pesan_error). Kartu tak dikenal dicatat agar bisa didaftarkan admin."""
    cands = candidates(text)
    if not cands:
        return None, "Kartu tidak dikenali"
    marks = ",".join("?" for _ in cands)
    row = query("SELECT s.*, k.nama AS kelas_nama, k.jenjang FROM siswa s "
                f"LEFT JOIN kelas k ON k.id = s.kelas_id WHERE s.rfid_uid IN ({marks})",
                cands, one=True, db=db)
    if row is not None:
        return row, None
    blok = query("SELECT b.*, s.nama FROM rfid_blokir b LEFT JOIN siswa s ON s.id = b.siswa_id "
                 f"WHERE b.uid IN ({marks}) ORDER BY b.id DESC LIMIT 1", cands, one=True, db=db)
    if blok is not None:
        return None, (f"Kartu diblokir ({blok['alasan'] or 'hilang'})"
                      + (f" — milik {blok['nama']}" if blok["nama"] else ""))
    catat_tak_dikenal(cands[0], db=db)
    return None, "Kartu RFID belum terdaftar"


def catat_tak_dikenal(uid, perangkat=None, db=None):
    execute("INSERT INTO rfid_tak_dikenal(uid, perangkat, waktu) VALUES (?,?,?) "
            "ON DUPLICATE KEY UPDATE perangkat = VALUES(perangkat), waktu = VALUES(waktu)",
            (uid, perangkat, utils.now().strftime("%Y-%m-%d %H:%M:%S")), db=db, commit=False)


def pemilik(uid, db=None):
    """Siswa yang sudah memakai UID ini (bentuk apa pun), atau None."""
    cands = candidates(uid)
    if not cands:
        return None
    marks = ",".join("?" for _ in cands)
    return query(f"SELECT id, nama FROM siswa WHERE rfid_uid IN ({marks})", cands, one=True, db=db)


def pasang(siswa_id, text, db=None):
    """Daftarkan kartu ke siswa. Mengembalikan (ok, pesan)."""
    uid = normalize(text)
    if uid is None:
        return False, "Isi bukan UID kartu RFID yang valid"
    lain = pemilik(uid, db=db)
    if lain and lain["id"] != siswa_id:
        return False, f"Kartu ini sudah terdaftar untuk {lain['nama']}"
    cands = candidates(uid)
    marks = ",".join("?" for _ in cands)
    execute(f"DELETE FROM rfid_blokir WHERE uid IN ({marks})", cands, db=db, commit=False)
    execute(f"DELETE FROM rfid_tak_dikenal WHERE uid IN ({marks})", cands, db=db, commit=False)
    execute("UPDATE siswa SET rfid_uid = ? WHERE id = ?", (uid, siswa_id), db=db)
    return True, "Kartu terdaftar"


def lepas(siswa_id, blokir=False, alasan="Hilang", db=None):
    """Lepas kartu dari siswa; bila `blokir`, kartu lama ditolak bila di-tap lagi."""
    r = query("SELECT rfid_uid FROM siswa WHERE id = ?", (siswa_id,), one=True, db=db)
    if not r or not r["rfid_uid"]:
        return False
    if blokir:
        execute("INSERT INTO rfid_blokir(uid, siswa_id, alasan, waktu) VALUES (?,?,?,?)",
                (r["rfid_uid"], siswa_id, alasan, utils.now().strftime("%Y-%m-%d %H:%M:%S")),
                db=db, commit=False)
    execute("UPDATE siswa SET rfid_uid = NULL WHERE id = ?", (siswa_id,), db=db)
    return True
