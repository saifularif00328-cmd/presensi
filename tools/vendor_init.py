"""Buat pasangan kunci lisensi vendor (SEKALI saja).

    python tools/vendor_init.py

- vendor/private_key.pem  → KUNCI PRIVAT. Simpan baik-baik & buat cadangan (flashdisk).
                             Jangan pernah dibagikan / di-commit ke Git.
- app/license_public.pem  → kunci publik, ikut dibundel di aplikasi sekolah.

Bila kunci privat hilang, lisensi baru tidak bisa dibuat untuk aplikasi yang sudah
tersebar. Jika kunci diganti, semua aplikasi harus di-build ulang dan lisensi lama
harus diterbitkan ulang.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.license import generate_keypair  # noqa: E402

PRIV = os.path.join(ROOT, "vendor", "private_key.pem")
PUB = os.path.join(ROOT, "app", "license_public.pem")

if __name__ == "__main__":
    if os.path.exists(PRIV) and "--paksa" not in sys.argv:
        print(f"Kunci privat sudah ada: {PRIV}\n"
              "Tidak dibuat ulang (gunakan --paksa untuk mengganti — lisensi lama jadi tidak berlaku).")
        sys.exit(0)
    os.makedirs(os.path.dirname(PRIV), exist_ok=True)
    priv, pub = generate_keypair()
    with open(PRIV, "wb") as f:
        f.write(priv)
    with open(PUB, "wb") as f:
        f.write(pub)
    print("Kunci vendor dibuat.")
    print(f"  Kunci privat : {PRIV}   <-- RAHASIAKAN & BACKUP")
    print(f"  Kunci publik : {PUB}    <-- ikut aplikasi sekolah")
    print("Build ulang aplikasi (.exe) agar memakai kunci publik ini.")
