"""QR code kartu siswa.

Isi QR: ``PSD1.<qr_token>.<checksum>`` — hanya ID unik siswa + checksum HMAC,
bukan data pribadi. Checksum memakai secret per-instalasi sehingga kartu tidak
bisa dipalsukan hanya dengan menebak ID, dan kartu lama otomatis tidak berlaku
saat token siswa diganti (cetak ulang kartu).
"""
import base64
import hashlib
import hmac
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from .db import get_setting, query

PREFIX = "PSD1"


def _checksum(token, secret):
    mac = hmac.new(secret.encode(), token.encode(), hashlib.sha256).digest()
    return base64.b32encode(mac)[:8].decode()


def make_payload(qr_token, db=None):
    return f"{PREFIX}.{qr_token}.{_checksum(qr_token, get_setting('qr_secret', db=db))}"


def parse_payload(text, db=None):
    """Kembalikan qr_token bila payload valid, None bila palsu/rusak."""
    if not text:
        return None
    text = text.strip().upper()
    parts = text.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None
    token, check = parts[1], parts[2]
    expected = _checksum(token, get_setting("qr_secret", db=db))
    if not hmac.compare_digest(check, expected):
        return None
    return token


def find_siswa(text, db=None):
    """Cari siswa dari hasil scan. Mengembalikan (row, pesan_error)."""
    token = parse_payload(text, db=db)
    if token is None:
        return None, "QR tidak valid / bukan kartu presensi sekolah ini"
    row = query("SELECT s.*, k.nama AS kelas_nama, k.jenjang FROM siswa s "
                "LEFT JOIN kelas k ON k.id = s.kelas_id WHERE s.qr_token = ?",
                (token,), one=True, db=db)
    if row is None:
        return None, "Kartu sudah tidak berlaku (mungkin sudah dicetak ulang)"
    if not row["aktif"]:
        return None, f"Siswa {row['nama']} berstatus nonaktif"
    return row, None


def qr_png(data, box_size=8, border=2):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
