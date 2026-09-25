"""Buat gambar pratinjau template kartu (app/static/img/kartu/<template>-<h|v>.png).

    python tools/build_card_previews.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PRESENSI_DATA_DIR", tempfile.mkdtemp())

from app import create_app  # noqa: E402
from app.services.kartu import ORIENTASI, TEMPLATES, kartu_pdf, pdf_to_png  # noqa: E402

SAMPLE = {"nama": "Aisyah Putri Ramadhani", "nis": "2024001", "nisn": "0098765432",
          "kelas_nama": "7A", "foto": None, "qr_token": "A1B2C3D4E5F60718"}


def main(warna="biru", out=None, scale=2.5):
    out = out or os.path.join(ROOT, "app", "static", "img", "kartu")
    os.makedirs(out, exist_ok=True)
    app = create_app({"TESTING": True}, start_jobs=False)
    with app.app_context():
        for t in TEMPLATES:
            for o in ORIENTASI:
                info = {"sekolah": "SMP Negeri 1 Nusantara",
                        "alamat": "Jl. Pendidikan No. 1, Kota Nusantara"}
                pdf = kartu_pdf([SAMPLE], info, t, o, warna, preview=True)
                with open(os.path.join(out, f"{t}-{o}.png"), "wb") as f:
                    f.write(pdf_to_png(pdf, scale).read())
    print("Pratinjau disimpan di", out)


if __name__ == "__main__":
    main(*sys.argv[1:2])
