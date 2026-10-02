"""Tahap 1 — keamanan data: backup ke Google Drive (rclone crypt), uji pulih, cek kesehatan + alarm."""
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

from tests.test_vps import vps  # noqa: F401 — fixture tools/sekolah.py + MySQL root

RCLONE_PALSU = os.path.join(os.path.dirname(__file__), "alat", "rclone_palsu.py")


@pytest.fixture
def drive(vps, tmp_path, monkeypatch):  # noqa: F811
    sk, dibuat = vps
    awan = tmp_path / "awan"
    (awan / "gdrive").mkdir(parents=True)          # remote "gdrive:" sudah dihubungkan (rclone config)
    monkeypatch.setenv("RCLONE_PALSU", str(awan))
    monkeypatch.setenv("PRESENSI_RCLONE", RCLONE_PALSU)
    terkirim = []
    monkeypatch.setattr(sk, "_beritahu_vendor", terkirim.append)
    return sk, dibuat, awan, terkirim


def _isi_siswa(sk, kode):
    from app.db import connect
    s = sk.muat()[kode]
    db = connect({"host": "127.0.0.1", "port": 3306, "user": s["db_user"],
                  "password": s["db_pass"], "database": s["db"]})
    db.execute("INSERT INTO kelas(nama, jenjang) VALUES ('7A', '7')")
    db.execute("INSERT INTO siswa(nama, kelas_id, qr_token, aktif) VALUES ('Uji Satu', 1, 'AB12CD34', 1)")
    db.commit()
    db.close()


def test_backup_drive_uji_pulih_dan_ambil(drive, capsys):
    sk, dibuat, awan, _ = drive
    dibuat.append("uji-k1")
    sk.main(["tambah", "uji-k1", "--nama", "SMP Uji K1", "--hari", "30"])
    _isi_siswa(sk, "uji-k1")
    # belum dipasang: backup harian tetap jalan, Drive dilewati
    sk.main(["backup", "--semua"])
    assert sk.baca_status()["backup"]["ok"] and "drive" not in sk.baca_status()
    # pasang: crypt di atas gdrive, sandi disimpan & ditampilkan sekali
    with pytest.raises(SystemExit):
        sk.main(["backup-drive", "--pasang", "--remote", "belumada:x"])
    sk.main(["backup-drive", "--pasang"])
    keluar = capsys.readouterr().out
    r = sk._rahasia()
    assert r["drive_sandi"] in keluar and r["drive_sandi2"] in keluar
    conf = (awan / "presensi-aman.conf").read_text()
    assert "crypt" in conf and "remote=gdrive:presensi-backup" in conf and "--obscure" in conf
    assert oct(os.stat(os.path.join(sk.ROOT, "_rahasia.json")).st_mode)[-3:] == "600"
    # backup malam: lokal + Drive
    sk.main(["backup", "--semua"])
    st = sk.baca_status()
    assert st["backup"]["ok"] and st["drive"]["ok"] and st["drive"]["jumlah_berkas"] == 1
    assert any(f.startswith("uji-k1-") for f in os.listdir(awan / "presensi-aman"))
    # uji pulih mengambil dari Drive, memulihkan ke database sementara
    sk.main(["uji-pulih"])
    u = sk.baca_status()["uji_pulih"]
    assert u["ok"] and u["dari"] == "drive" and u["hasil"]["uji-k1"]["siswa"] == 1
    import pymysql
    c = pymysql.connect(unix_socket="/run/mysqld/mysqld.sock", user="root")
    with c.cursor() as cur:
        cur.execute("SHOW DATABASES LIKE 'presensi_ujipulih'")
        assert cur.fetchone() is None                     # database sementara sudah dihapus
    c.close()
    # pemulihan bencana: unduh backup terbaru tiap sekolah
    berkas = sk.main(["ambil-drive"])
    assert len(berkas) == 1 and os.path.exists(os.path.join(sk.ROOT, "_pulih", berkas[0]))
    d = json.load(open(os.path.join(sk.ROOT, "_pulih", "daftar-sekolah.json")))
    assert d["sekolah"]["uji-k1"]["nama"] == "SMP Uji K1" and "db_pass" not in d["sekolah"]["uji-k1"]


def test_uji_pulih_gagal_tercatat(drive):
    sk, dibuat, _, _ = drive
    dibuat.append("uji-k2")
    sk.main(["tambah", "uji-k2", "--nama", "SMP Uji K2"])
    rusak = os.path.join(sk.ROOT, "_backup", f"uji-k2-{datetime.now():%Y-%m-%d}.zip")
    os.makedirs(os.path.dirname(rusak), exist_ok=True)
    with open(rusak, "wb") as f:
        f.write(b"bukan zip")
    with pytest.raises(SystemExit):
        sk.main(["uji-pulih", "uji-k2"])
    u = sk.baca_status()["uji_pulih"]
    assert not u["ok"] and u["gagal"] == ["uji-k2"] and u["dari"] == "lokal"
    masalah, _ = sk.periksa()
    assert any(m["kode"] == "uji_pulih" and m["tingkat"] == "kritis" for m in masalah)


def test_drive_gagal_tercatat(drive, monkeypatch):
    sk, dibuat, _, _ = drive
    dibuat.append("uji-k3")
    sk.main(["tambah", "uji-k3", "--nama", "SMP Uji K3"])
    sk.main(["backup-drive", "--pasang"])
    monkeypatch.setenv("RCLONE_PALSU_GAGAL", "copy")
    with pytest.raises(SystemExit):
        sk.main(["backup", "--semua"])
    st = sk.baca_status()
    assert st["backup"]["ok"] and not st["drive"]["ok"]          # lokal tetap aman
    assert any(m["kode"] == "drive" for m in sk.periksa()[0])


def test_cek_kesehatan_alarm_dan_pulih(drive, monkeypatch):
    sk, dibuat, _, terkirim = drive
    reg = {"smpx": {"status": "aktif", "port": 7001, "nama": "X"}}
    monkeypatch.setattr(sk, "muat", lambda: reg)
    mati = {"nginx"}
    monkeypatch.setattr(sk, "_layanan_aktif", lambda n: n not in mati)
    t0 = datetime(2030, 1, 7, 8, 0)
    sk.catat_status("backup", ok=True, jumlah=1, gagal=[])
    data, pesan = sk.cek_kesehatan(sekarang=t0)
    assert pesan and "nginx mati" in pesan and len(terkirim) == 1
    assert any(m["kode"] == "drive" and m["tingkat"] == "peringatan" for m in data["masalah"])
    # masalah sama 10 menit kemudian: tidak mengirim ulang
    assert sk.cek_kesehatan(sekarang=t0 + timedelta(minutes=10))[1] is None
    # masalah baru (sekolah mati) langsung dikabari
    mati.add("presensi@smpx")
    assert "smpx" in sk.cek_kesehatan(sekarang=t0 + timedelta(minutes=20))[1]
    # pulih
    mati.clear()
    assert "normal kembali" in sk.cek_kesehatan(sekarang=t0 + timedelta(minutes=30))[1]
    assert sk.cek_kesehatan(sekarang=t0 + timedelta(minutes=40))[1] is None
    # backup terlambat > 26 jam = kritis
    st = sk.baca_status()
    st["backup"]["waktu"] = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")
    sk._tulis_json(sk._status_path(), st)
    assert any(m["kode"] == "backup" and m["tingkat"] == "kritis" for m in sk.periksa()[0])


def test_halaman_sehat_dan_panel(drive, tmp_path, monkeypatch):
    sk, _, _, _ = drive
    monkeypatch.setenv("PRESENSI_SRV", sk.ROOT)
    from daftar import create_app
    web = create_app({"TESTING": True, "SECRET_KEY": "uji"}).test_client()
    assert web.get("/sehat").status_code == 503                  # pemeriksaan belum berjalan
    monkeypatch.setattr(sk, "muat", lambda: {})
    sk.cek_kesehatan()
    r = web.get("/sehat")
    assert r.status_code == 200 and r.get_data(as_text=True) == "ok"
    k = json.load(open(os.path.join(sk.ROOT, "_kesehatan.json")))
    k["masalah"] = [{"kode": "layanan:nginx", "tingkat": "kritis", "pesan": "Layanan nginx mati"}]
    sk._tulis_json(os.path.join(sk.ROOT, "_kesehatan.json"), k)
    r = web.get("/sehat")
    assert r.status_code == 503 and "nginx" not in r.get_data(as_text=True)
    # panel vendor menampilkan kartu kesehatan
    import daftar.vendor as v
    v._gagal.clear()
    v._kode_terpakai.clear()
    rahasia = sk.main(["akun-vendor", "--password", "sangat-rahasia-1", "--tanpa-qr"])
    web.post("/vendor/masuk", data={"username": "vendor", "password": "sangat-rahasia-1",
                                    "kode": v.totp(rahasia)})
    html = web.get("/vendor/").get_data(as_text=True)
    assert "Server bermasalah" in html and "Layanan nginx mati" in html
    assert "Uji pulih" in web.get("/vendor/pengaturan").get_data(as_text=True)


def test_rclone_palsu_tersedia():
    assert os.access(RCLONE_PALSU, os.X_OK) and sys.executable
