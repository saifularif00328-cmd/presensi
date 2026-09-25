"""Generator kode lisensi (khusus vendor).

Pemakaian:
    python tools/keygen.py <ID_PERANGKAT> <basic|pro|enterprise>

ID perangkat terlihat di menu Akun → Lisensi pada aplikasi sekolah.
VENDOR_SECRET di app/license.py harus sama dengan yang dipakai saat build aplikasi.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.license import make_key  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    print(make_key(sys.argv[1], sys.argv[2]))
