"""Halaman depan + pendaftaran demo (daftar/), antrean root (tools/sekolah.py), popup perpanjang."""
import json
import os
import re
from urllib.parse import unquote

import pytest

from tests.test_vps import vps  # noqa: F401 — fixture tools/sekolah.py + MySQL root


def _isi(**ubah):
    data = {"nama_sekolah": "SMP Negeri 9 Uji", "jenjang": "SMP / MTs", "kota": "Kota Malang",
            "zona": "Asia/Jakarta", "nama": "Budi Operator", "jabatan": "Operator",
            "wa": "0812-3456-7890", "email": "", "jumlah_siswa": "450", "kode": "smpn9uji",
            "password": "rahasia-kuat-1", "password2": "rahasia-kuat-1", "setuju": "1"}
    data.update(ubah)
    return data


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENSI_SRV", str(tmp_path / "srv"))
    os.makedirs(tmp_path / "srv", exist_ok=True)
    return tmp_path / "srv"


@pytest.fixture
def web(srv):
    from daftar import create_app
    app = create_app({"TESTING": True, "SECRET_KEY": "uji", "WAKTU_ISI_MIN": 0})
    return app.test_client()


def _kirim(web, **ubah):
    html = web.get("/").get_data(as_text=True)
    t = re.search(r'name="t" value="([^"]+)"', html).group(1)
    return web.post("/daftar", data={**_isi(**ubah), "t": t})


def _tulis(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_beranda_dan_pendaftaran_masuk_antrean(web, srv):
    r = web.get("/")
    assert r.status_code == 200 and "Daftar demo gratis 7 hari" in r.get_data(as_text=True)
    r = _kirim(web)
    assert r.status_code == 302
    token = r.headers["Location"].rsplit("/", 1)[1]
    berkas = srv / "_antrean" / "masuk" / f"{token}.json"
    p = json.loads(berkas.read_text())
    assert p["kode"] == "smpn9uji" and p["wa"] == "6281234567890"
    assert p["password_hash"].startswith(("scrypt:", "pbkdf2:"))
    assert "rahasia-kuat-1" not in berkas.read_text()          # password tidak tersimpan polos
    assert web.get(f"/daftar/{token}/status").get_json()["status"] == "menunggu"
    assert web.get(f"/daftar/{token}").status_code == 200
    # kode & nomor WA yang sedang antre tidak bisa dipakai lagi
    assert web.get("/cek-kode?kode=smpn9uji").get_json()["ok"] is False
    r = _kirim(web, kode="lain123")
    assert r.status_code == 400 and "sudah pernah mendaftar" in r.get_data(as_text=True)
    assert web.get("/daftar/tidak-ada-token-ini").status_code == 404


def test_pendaftaran_ditolak(web, srv):
    assert _kirim(web, situs="http://spam").status_code == 400            # kolom jebakan bot
    r = _kirim(web, kode="admin")
    assert r.status_code == 400 and "tidak bisa dipakai" in r.get_data(as_text=True)
    _tulis(srv / "_publik.json", {"kode": ["smpn1"], "demo_aktif": 0})
    assert "sudah dipakai" in _kirim(web, kode="smpn1").get_data(as_text=True)
    r = _kirim(web, wa="12345", password2="beda", setuju="")
    html = r.get_data(as_text=True)
    assert "WhatsApp tidak valid" in html and "sama persis" in html and "Centang" in html
    assert not os.listdir(srv / "_antrean" / "masuk") if (srv / "_antrean").exists() else True
    # kuota demo penuh: formulir diganti pesan + tombol WhatsApp
    _tulis(srv / "_konfigurasi.json", {"wa": "6285700001111", "maks_demo": 1})
    _tulis(srv / "_publik.json", {"kode": [], "demo_aktif": 1})
    html = web.get("/").get_data(as_text=True)
    assert "Kuota demo sedang penuh" in html and "wa.me/6285700001111" in html
    assert 'id="form-daftar"' not in html


def test_halaman_privasi(web, srv):
    _tulis(srv / "_konfigurasi.json", {"wa": "6285700001111", "nama": "Presensiku"})
    html = web.get("/privasi").get_data(as_text=True)
    assert "Kebijakan privasi" in html and "wa.me/6285700001111" in html
    assert 'href="/privasi"' in web.get("/").get_data(as_text=True)


def test_formulir_terlalu_cepat_ditolak(srv):
    from daftar import create_app
    web = create_app({"TESTING": True, "SECRET_KEY": "uji", "WAKTU_ISI_MIN": 60}).test_client()
    assert _kirim(web).status_code == 400


def test_halaman_demo_berakhir(web, srv):
    _tulis(srv / "_konfigurasi.json", {"wa": "6285700001111", "nama": "Presensiku"})
    html = web.get("/?berakhir=smpn9uji").get_data(as_text=True)
    assert "telah berakhir" in html and "wa.me/6285700001111?text=" in html
    assert "smpn9uji" in unquote(re.search(r'href="(https://wa.me/[^"]+)"', html).group(1))
    assert "telah berakhir" not in web.get("/?berakhir=<script>").get_data(as_text=True)


def test_antrean_membuat_sekolah_demo(vps, web, srv):  # noqa: F811
    sk, dibuat = vps
    dibuat.append("smpn9uji")
    assert os.environ["PRESENSI_SRV"] == sk.ROOT == str(srv)
    sk.main(["setel", "--wa", "085700001111", "--hari-demo", "7", "--maks-demo", "3"])
    token = _kirim(web).headers["Location"].rsplit("/", 1)[1]
    sk.main(["proses-antrean"])
    assert not os.listdir(srv / "_antrean" / "masuk")
    st = web.get(f"/daftar/{token}/status").get_json()
    assert st["status"] == "siap" and st["kode"] == "smpn9uji" and st["username"] == "admin"
    s = sk.muat()["smpn9uji"]
    assert s["status"] == "uji_coba" and s["pendaftar"]["wa"] == "6281234567890"
    v = json.loads((srv / "smpn9uji" / "data" / "_vendor.json").read_text())
    assert v["wa_vendor"] == "6285700001111" and v["demo"] is True and v["kode"] == "smpn9uji"
    pub = json.loads((srv / "_publik.json").read_text())
    assert "smpn9uji" in pub["kode"] and pub["demo_aktif"] == 1
    # admin memakai password dari formulir, tanpa wajib ganti
    from werkzeug.security import check_password_hash

    from app.db import connect
    db = connect({"host": "127.0.0.1", "port": 3306, "user": s["db_user"],
                  "password": s["db_pass"], "database": s["db"]})
    u = db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    db.close()
    assert check_password_hash(u["password_hash"], "rahasia-kuat-1") and u["wajib_ganti"] == 0
    assert u["nama"] == "Budi Operator"
    # kode yang sudah jadi tidak bisa didaftarkan lagi
    assert web.get("/cek-kode?kode=smpn9uji").get_json()["ok"] is False

    # demo lama berakhir -> layanan dihentikan, alamat diarahkan ke halaman depan
    reg = sk.muat()
    reg["smpn9uji"]["sampai"] = "2020-01-01"
    sk.simpan(reg)
    sk.main(["rapikan"])
    assert sk.muat()["smpn9uji"]["status"] == "berhenti"
    conf = open(sk.NGINX_CONF).read()
    assert "return 302 /?berakhir=smpn9uji;" in conf and "proxy_pass http://127.0.0.1:" not in conf
    # setelah bayar: perpanjang -> aktif & alamat kembali ke aplikasi
    sk.main(["perpanjang", "smpn9uji", "--hari", "365"])
    assert sk.muat()["smpn9uji"]["status"] == "aktif"
    assert "X-Forwarded-Prefix /smpn9uji;" in open(sk.NGINX_CONF).read()


def test_antrean_tolak_data_rusak(vps, srv):  # noqa: F811
    sk, _ = vps
    masuk = srv / "_antrean" / "masuk"
    _tulis(masuk / "AAAAAAAAAAAAAAAAAAAAAAAA.json",
           {"kode": "Bukan Kode!", "nama_sekolah": "X", "password_hash": "polos"})
    sk.main(["proses-antrean"])
    h = json.loads((srv / "_antrean" / "hasil" / "AAAAAAAAAAAAAAAAAAAAAAAA.json").read_text())
    assert h["status"] == "gagal" and "password_hash" not in h
    assert sk.muat() == {}


def _vendor_cloud(monkeypatch, tmp_path, **v):
    from app import config
    monkeypatch.setenv("PRESENSI_MODE", "cloud")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    _tulis(tmp_path / "_vendor.json", {"maks_siswa": 0, "sekolah": "SMP Uji", "kode": "smpuji",
                                       "demo": True, "wa_vendor": "6285700001111",
                                       "nama_vendor": "Presensiku", **v})


def test_popup_perpanjang_saat_demo_habis(client, seed, monkeypatch, tmp_path):
    _vendor_cloud(monkeypatch, tmp_path, status="uji_coba", berlaku_sampai="2030-01-01")
    html = client.get("/").get_data(as_text=True)
    assert 'id="modal-perpanjang" data-wajib="1"' in html and "mode baca-saja" in html
    url = unquote(re.search(r'href="(https://wa\.me/6285700001111\?text=[^"]+)"', html).group(1))
    assert "smpuji" in url and "sudah berakhir" in url and "Jumlah siswa aktif: 3" in url
    assert "Masa demo" in url
    # mode baca-saja tetap berlaku
    assert client.post("/presensi/api/scan", json={"code": seed["ahmad"]["qr"]}).status_code == 402


def test_popup_menjelang_berakhir_bisa_ditutup(client, monkeypatch, tmp_path):
    _vendor_cloud(monkeypatch, tmp_path, status="uji_coba", berlaku_sampai="2030-01-08")
    html = client.get("/").get_data(as_text=True)
    assert 'data-wajib="0"' in html and "akan berakhir" in unquote(html)
    # tanpa nomor WA vendor: tidak ada popup, hanya banner biasa
    _vendor_cloud(monkeypatch, tmp_path, status="uji_coba", berlaku_sampai="2030-01-01",
                  wa_vendor="")
    html = client.get("/").get_data(as_text=True)
    assert "modal-perpanjang" not in html and "Masa langganan berakhir" in html
