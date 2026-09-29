import os
import tempfile
from datetime import datetime

_TMP = tempfile.mkdtemp(prefix="presensi-test-")
os.environ["PRESENSI_DATA_DIR"] = _TMP
os.environ["PRESENSI_DEVICE_ID"] = "TEST-DEVI-CE00-0001"

# Pasangan kunci lisensi khusus pengujian (kunci publik lewat env)
from cryptography.hazmat.primitives import serialization  # noqa: E402

from app.license import generate_keypair  # noqa: E402

_PRIV_PEM, _PUB_PEM = generate_keypair()
os.environ["PRESENSI_LICENSE_PUBKEY"] = _PUB_PEM.decode()
PRIV_KEY = serialization.load_pem_private_key(_PRIV_PEM, password=None)
PRIV_PEM = _PRIV_PEM

import pytest  # noqa: E402

from app import create_app, utils  # noqa: E402
from app.db import connect, set_setting  # noqa: E402
from app.license import make_license  # noqa: E402

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


# Server MySQL/MariaDB untuk pengujian; setiap tes memakai database sementara sendiri.
TEST_DB_URL = os.environ.get("PRESENSI_TEST_DB_URL", "mysql://presensi:presensi@127.0.0.1:3306/")


@pytest.fixture
def make_db():
    """Pabrik konfigurasi database sementara; semua dihapus setelah tes selesai."""
    import uuid
    from urllib.parse import unquote, urlparse

    import pymysql
    u = urlparse(TEST_DB_URL)
    base = {"host": u.hostname, "port": u.port or 3306, "user": unquote(u.username or "root"),
            "password": unquote(u.password or "")}
    dibuat = []

    def buat():
        cfg = dict(base, database="presensi_test_" + uuid.uuid4().hex[:10])
        dibuat.append(cfg["database"])
        return cfg

    yield buat
    conn = pymysql.connect(**base)
    with conn.cursor() as cur:
        for name in dibuat:
            cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
    conn.close()


@pytest.fixture
def app(make_db, clock):
    app = create_app({"TESTING": True, "DATABASE": make_db(), "WTF_CSRF_DISABLED": True},
                     start_jobs=False)
    return app


def set_tier(app, tier):
    with app.app_context():
        db = connect()
        set_setting("license_key", make_license(PRIV_KEY, os.environ["PRESENSI_DEVICE_ID"], tier,
                                                "Sekolah Uji") if tier else "", db=db)
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
