"""Alat vendor VPS (tools/sekolah.py): tambah sekolah, langganan, pindah dari server sekolah."""
import json
import os

import pytest

from app.db import connect


@pytest.fixture
def vps(tmp_path, monkeypatch):
    """tools/sekolah.py dengan folder sementara, tanpa systemctl/nginx (butuh akses root MySQL)."""
    import pymysql
    try:
        pymysql.connect(unix_socket="/run/mysqld/mysqld.sock", user="root").close()
    except pymysql.Error:
        pytest.skip("butuh akses root MySQL lewat socket")
    monkeypatch.setenv("PRESENSI_TANPA_SISTEM", "1")
    monkeypatch.setenv("PRESENSI_SRV", str(tmp_path / "srv"))
    monkeypatch.setenv("PRESENSI_NGINX_CONF", str(tmp_path / "nginx" / "presensi-sekolah.conf"))
    import importlib
    import tools.sekolah as sk
    importlib.reload(sk)
    dibuat = []
    yield sk, dibuat
    conn = pymysql.connect(unix_socket="/run/mysqld/mysqld.sock", user="root", autocommit=True)
    with conn.cursor() as c:
        for kode in dibuat:
            k = kode.replace("-", "_")
            c.execute(f"DROP DATABASE IF EXISTS `presensi_{k}`")
            c.execute(f"DROP USER IF EXISTS 'p_{k}'@'localhost'")
    conn.close()


def _vendor(sk, kode):
    with open(os.path.join(sk.ROOT, kode, "data", "_vendor.json")) as f:
        return json.load(f)


def test_vps_tambah_perpanjang_nonaktif(vps):
    sk, dibuat = vps
    dibuat.append("uji-a")
    s = sk.main(["tambah", "uji-a", "--nama", "SMP Uji A", "--sampai", "2031-06-30",
                 "--maks-siswa", "800", "--zona", "Asia/Makassar"])
    assert s["port"] == 7001
    env = open(os.path.join(sk.ROOT, "uji-a", "env")).read()
    assert "PRESENSI_MODE=cloud" in env and "PRESENSI_PORT=7001" in env
    v = _vendor(sk, "uji-a")
    assert v["status"] == "aktif" and v["maks_siswa"] == 800
    from app.db import get_setting
    db = connect({"host": "127.0.0.1", "port": 3306, "user": s["db_user"],
                  "password": s["db_pass"], "database": s["db"]})
    assert get_setting("nama_sekolah", db=db) == "SMP Uji A"
    assert get_setting("zona_waktu", db=db) == "Asia/Makassar"
    assert get_setting("alamat_publik", db=db) == f"https://{sk.DOMAIN}/uji-a"
    db.close()
    conf = open(sk.NGINX_CONF).read()
    assert "location /uji-a/" in conf and "proxy_pass http://127.0.0.1:7001/;" in conf
    assert "X-Forwarded-Prefix /uji-a;" in conf
    sk.main(["perpanjang", "uji-a", "--hari", "30"])
    assert _vendor(sk, "uji-a")["berlaku_sampai"] == "2031-07-30"  # menyambung dari tanggal habis
    sk.main(["nonaktif", "uji-a"])
    assert _vendor(sk, "uji-a")["status"] == "nonaktif"
    with pytest.raises(SystemExit):
        sk.main(["tambah", "uji-a", "--nama", "ganda"])
    with pytest.raises(SystemExit):
        sk.main(["tambah", "Bukan Kode!", "--nama", "x"])


def test_vps_pindah_dari_server_sekolah(vps, app, client, seed, monkeypatch):
    """Backup ZIP dari server sekolah dipulihkan utuh di VPS; langganan tetap dari vendor."""
    sk, dibuat = vps
    dibuat.append("uji-b")
    client.post("/presensi/api/scan", json={"code": seed["ahmad"]["qr"], "mode": "auto"})
    zip_data = client.get("/sistem/backup").data
    zip_path = os.path.join(sk.ROOT, "..", "smpn-uji.zip")
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with open(zip_path, "wb") as f:
        f.write(zip_data)
    sk.main(["pindah", "uji-b", zip_path, "--nama", "SMP Uji B", "--sampai", "2031-01-01"])
    s = sk.muat()["uji-b"]
    db = connect({"host": "127.0.0.1", "port": 3306, "user": s["db_user"],
                  "password": s["db_pass"], "database": s["db"]})
    assert db.execute("SELECT COUNT(*) AS n FROM siswa").fetchone()["n"] == 3
    assert db.execute("SELECT COUNT(*) AS n FROM presensi").fetchone()["n"] == 1
    assert db.execute("SELECT nilai FROM settings WHERE kunci = 'alamat_publik'").fetchone()[0] \
        == f"https://{sk.DOMAIN}/uji-b"
    db.close()
    assert _vendor(sk, "uji-b")["berlaku_sampai"] == "2031-01-01"
    sk.main(["backup", "uji-b"])
    assert any(f.startswith("uji-b-") for f in os.listdir(os.path.join(sk.ROOT, "_backup")))


def test_pasang_pos_dari_github(vps, tmp_path, monkeypatch):
    """`pasang-pos --github`: rilis pos-vX.Y.Z terbaru diunduh lalu dipasang di /unduh/."""
    import argparse
    import io
    import json
    import urllib.request
    sk, _ = vps
    rilis = [{"tag_name": "v9-lain", "assets": [{"name": "lain.zip", "browser_download_url": "x"}]},
             {"tag_name": "pos-v1.2.0", "draft": False,
              "assets": [{"name": "presensiku-pos-setup.exe", "browser_download_url": "https://contoh/setup.exe"}]}]
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: io.BytesIO(json.dumps(rilis).encode()))
    diunduh = []

    def palsu_retrieve(url, path):
        diunduh.append(url)
        with open(path, "wb") as f:
            f.write(b"MZ-installer")
    monkeypatch.setattr(urllib.request, "urlretrieve", palsu_retrieve)
    sk.pasang_pos(argparse.Namespace(berkas=None, versi=None, github=True))
    assert diunduh == ["https://contoh/setup.exe"]
    with open(os.path.join(sk.ROOT, "_unduh", "presensiku-pos-setup.exe"), "rb") as f:
        assert f.read() == b"MZ-installer"
    with open(os.path.join(sk.ROOT, "_unduh", "pos-versi.json")) as f:
        assert json.load(f)["versi"] == "1.2.0"
    with pytest.raises(SystemExit):
        sk.pasang_pos(argparse.Namespace(berkas=None, versi=None, github=False))
