"""Buat kode lisensi secara OFFLINE (tanpa server aktivasi) — khusus vendor.

Contoh:
    python tools/keygen.py --device A1B2-C3D4-E5F6-7890 --tier pro --sekolah "SMPN 1 Contoh" --hari 365
    python tools/keygen.py --device A1B2-C3D4-E5F6-7890 --tier enterprise --selamanya

ID perangkat terlihat di aplikasi sekolah: Akun → Lisensi.
Butuh kunci privat dari `python tools/vendor_init.py`.
"""
import argparse
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.license import TIERS, load_private_key, make_license  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generator kode lisensi Presensi Siswa Digital")
    ap.add_argument("--device", required=True, help="ID perangkat sekolah")
    ap.add_argument("--tier", required=True, choices=TIERS)
    ap.add_argument("--sekolah", default="", help="Nama sekolah (tercantum di lisensi)")
    ap.add_argument("--hari", type=int, default=365, help="Masa berlaku (hari), default 365")
    ap.add_argument("--selamanya", action="store_true", help="Tanpa tanggal kedaluwarsa")
    ap.add_argument("--kunci", default=os.path.join(ROOT, "vendor", "private_key.pem"))
    a = ap.parse_args()
    if not os.path.exists(a.kunci):
        sys.exit(f"Kunci privat tidak ditemukan: {a.kunci}\nJalankan dulu: python tools/vendor_init.py")
    exp = None if a.selamanya else date.today() + timedelta(days=a.hari)
    key = make_license(load_private_key(a.kunci), a.device, a.tier, a.sekolah, exp)
    print(f"Tier      : {a.tier}\nSekolah   : {a.sekolah or '-'}\nBerlaku   : {exp or 'selamanya'}\n")
    print(key)
