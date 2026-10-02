"""Salinan data siswa di PC (agar Layar Gerbang tetap menampilkan nama/foto saat offline).

Logika pengenalan kartu sengaja SAMA dengan server (app/qr.py & app/rfid.py) — diuji kesamaannya
di tests/test_pos_app.py.
"""
import base64
import hashlib
import hmac
import re

PREFIX = "PSD1"


# ---------------------------------------------------------------- QR (app/qr.py)
def checksum(token, secret):
    mac = hmac.new(secret.encode(), token.encode(), hashlib.sha256).digest()
    return base64.b32encode(mac)[:8].decode()


def parse_qr(text, secret):
    if not text or not secret:
        return None
    parts = text.strip().upper().split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None
    if not hmac.compare_digest(parts[2], checksum(parts[1], secret)):
        return None
    return parts[1]


# ---------------------------------------------------------------- RFID (app/rfid.py)
_HEX = re.compile(r"^[0-9A-F]+$")


def _bersih(text):
    return re.sub(r"[\s:\-_.]", "", (text or "").strip()).upper()


def looks_like_uid(text):
    t = _bersih(text)
    if t.isdigit():
        return 6 <= len(t) <= 20
    return bool(_HEX.match(t)) and len(t) % 2 == 0 and 8 <= len(t) <= 20


def uid_candidates(text):
    if not looks_like_uid(text):
        return []
    t = _bersih(text)
    if t.isdigit():
        n = int(t)
        b = n.to_bytes(max(4, (n.bit_length() + 7) // 8), "big")
    else:
        b = bytes.fromhex(t)
    return list(dict.fromkeys([b.hex().upper(), b[::-1].hex().upper()]))


def jenis(text):
    t = (text or "").strip().upper()
    if t.startswith(PREFIX + "."):
        return "qr"
    return "rfid" if looks_like_uid(t) else None


class DataSiswa:
    def __init__(self, data=None, secret=None):
        self.secret = secret
        self.isi(data or {})

    def isi(self, data):
        self.versi = data.get("versi")
        self.siswa = {s["id"]: s for s in data.get("siswa", [])}
        self.per_qr = {(s.get("qr_token") or "").upper(): s for s in self.siswa.values() if s.get("qr_token")}
        self.per_uid = {(s.get("rfid_uid") or "").upper(): s for s in self.siswa.values() if s.get("rfid_uid")}
        self.blokir = {u.upper() for u in data.get("blokir", [])}

    def cari(self, text):
        """(siswa | None, pesan_error | None, layak_kirim). `layak_kirim` False = pasti sampah."""
        j = jenis(text)
        if j == "qr":
            if not self.secret:
                return None, None, True          # belum sinkron: biarkan server yang memutuskan
            token = parse_qr(text, self.secret)
            if token is None:
                return None, "QR tidak valid / bukan kartu sekolah ini", False
            s = self.per_qr.get(token)
            return s, (None if s else "Kartu belum dikenal di PC ini"), True
        if j == "rfid":
            cands = uid_candidates(text)
            for c in cands:
                if c in self.per_uid:
                    return self.per_uid[c], None, True
            if any(c in self.blokir for c in cands):
                return None, "Kartu diblokir", True
            return None, "Kartu RFID belum terdaftar", True
        return None, "Kode tidak dikenali", False
