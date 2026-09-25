import os
import tempfile
from datetime import datetime

_TMP = tempfile.mkdtemp(prefix="presensi-test-")
os.environ["PRESENSI_DATA_DIR"] = _TMP
os.environ["PRESENSI_DEVICE_ID"] = "TEST-DEVI-CE00-0001"

import pytest  # noqa: E402

from app import create_app, utils  # noqa: E402
from app.db import connect, set_setting  # noqa: E402
from app.license import make_key  # noqa: E402

# Senin, 7 Januari 2030 — hari sekolah, setelah data siswa dibuat
BASE_DAY = datetime(2030, 1, 7)


class Clock:
    def __init__(self):
        self.value = BASE_DAY.replace(hour=6, minute=45)

    def set(self, hh, mm, day=None):
        d = day or self.value
        self.value = d.replace(hour=hh, minute=mm, second=0)

    def __call__(self):
        return self.value


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(utils, "now", c)
    return c


@pytest.fixture
def app(tmp_path, clock):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "t.db"),
                      "WTF_CSRF_DISABLED": True}, start_jobs=False)
    return app


def set_tier(app, tier):
    with app.app_context():
        db = connect()
        set_setting("license_key", make_key(os.environ["PRESENSI_DEVICE_ID"], tier) if tier else "",
                    db=db)
        db.close()


@pytest.fixture
def client(app):
    set_tier(app, "enterprise")
    c = app.test_client()
    r = c.post("/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 302
    return c


@pytest.fixture
def seed(app, client):
    """Dua kelas & tiga siswa. Mengembalikan dict id + payload QR."""
    from app.qr import make_payload
    client.post("/master/kelas", data={"nama": "7A", "jenjang": "7"})
    client.post("/master/kelas", data={"nama": "8A", "jenjang": "8"})
    for nama, kelas, wa in [("Ahmad Fauzi", 1, "081234567890"), ("Siti Aminah", 1, ""),
                            ("Budi Santoso", 2, "0812-9999-8888")]:
        client.post("/master/siswa/baru", data={"nama": nama, "kelas_id": kelas, "wa_ayah": wa,
                                                "jk": "L", "aktif": "1"})
    with app.app_context():
        db = connect()
        rows = db.execute("SELECT id, nama, qr_token FROM siswa ORDER BY id").fetchall()
        out = {r["nama"].split()[0].lower(): {"id": r["id"],
                                             "qr": make_payload(r["qr_token"], db=db)}
               for r in rows}
        db.close()
    return out
