"""Panel pribadi vendor (/vendor): login 2 langkah, perpanjang, tambah, nonaktif, pengaturan."""
import json

import pytest

from tests.test_vps import vps  # noqa: F401 — fixture tools/sekolah.py + MySQL root


def test_totp_vektor_rfc6238():
    from daftar.vendor import totp
    # RFC 6238 lampiran B (SHA1, kunci "12345678901234567890"), 6 digit terakhir
    assert totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59) == "287082"
    assert totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1111111109) == "081804"


@pytest.fixture
def panel(vps, tmp_path, monkeypatch):  # noqa: F811
    sk, dibuat = vps
    monkeypatch.setenv("PRESENSI_SRV", sk.ROOT)
    import daftar.vendor as v
    v._gagal.clear()
    v._kode_terpakai.clear()
    rahasia = sk.main(["akun-vendor", "--password", "sangat-rahasia-1", "--tanpa-qr"])
    from daftar import create_app
    app = create_app({"TESTING": True, "SECRET_KEY": "uji",
                      "JALANKAN_PEKERJA": lambda: sk.main(["proses-antrean"]),
                      "TUNGGU_PERINTAH": 2})
    return sk, dibuat, app.test_client(), rahasia, v


def _masuk(c, v, rahasia, kode=None, password="sangat-rahasia-1"):
    return c.post("/vendor/masuk", data={"username": "vendor", "password": password,
                                         "kode": kode or v.totp(rahasia)})


def _csrf(c):
    with c.session_transaction("/vendor/") as s:
        return s["csrf"]


def test_login_dua_langkah(panel):
    sk, _, c, rahasia, v = panel
    assert c.get("/vendor/").headers["Location"].endswith("/vendor/masuk")
    assert _masuk(c, v, rahasia, kode="000000").status_code == 401
    assert _masuk(c, v, rahasia, password="salah-password").status_code == 401
    r = _masuk(c, v, rahasia)
    assert r.status_code == 302 and "vendor_sesi=" in r.headers["Set-Cookie"]
    assert "Path=/vendor" in r.headers["Set-Cookie"] and "HttpOnly" in r.headers["Set-Cookie"]
    r = c.get("/vendor/")
    assert r.status_code == 200 and "Semua sekolah" in r.get_data(as_text=True)
    assert r.headers["Cache-Control"] == "no-store"
    # POST tanpa token CSRF ditolak
    assert c.post("/vendor/pengaturan", data={"wa": "0812"}).status_code == 400
    # kode authenticator yang sama tidak bisa dipakai ulang
    c.post("/vendor/keluar", data={"_csrf": _csrf(c)})
    assert _masuk(c, v, rahasia, kode=v.totp(rahasia)).status_code == 401


def test_login_dikunci_setelah_gagal(panel):
    _, _, c, rahasia, v = panel
    for _ in range(5):
        _masuk(c, v, rahasia, password="salah-terus")
    assert _masuk(c, v, rahasia).status_code == 429


def test_akun_diganti_sesi_lama_keluar(panel):
    sk, _, c, rahasia, v = panel
    _masuk(c, v, rahasia)
    assert c.get("/vendor/").status_code == 200
    sk.main(["akun-vendor", "--password", "password-baru-123", "--tanpa-qr"])
    assert c.get("/vendor/").status_code == 302


def test_kelola_sekolah_dari_panel(panel):
    sk, dibuat, c, rahasia, v = panel
    dibuat.append("smpn7uji")
    _masuk(c, v, rahasia)
    t = _csrf(c)
    # pengaturan vendor
    c.post("/vendor/pengaturan", data={"_csrf": t, "wa": "085711112222", "nama": "Presensiku",
                                       "hari_demo": "10", "maks_demo": "4", "henti_setelah": "21",
                                       "harga_tahun": "1.500.000", "harga_semester": "800000",
                                       "siswa_termasuk": "300", "harga_per_100": "250.000", "harga_pasang": "0"})
    k = sk.konfigurasi()
    assert k["wa"] == "6285711112222" and k["hari_demo"] == 10 and k["henti_setelah"] == 21
    assert k["harga_tahun"] == 1500000 and k["harga_per_100"] == 250000 and k["siswa_termasuk"] == 300
    # tambah sekolah berlangganan
    r = c.post("/vendor/tambah", data={
        "_csrf": t, "nama_sekolah": "SMP Negeri 7 Uji", "kode": "smpn7uji", "jenjang": "SMP / MTs",
        "kota": "Kota Batu", "zona": "Asia/Jakarta", "nama": "Sari", "wa": "081299990000",
        "jabatan": "TU", "hari": "365", "maks_siswa": "800", "password": "admin-sekolah-7"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/vendor/sekolah/smpn7uji")
    s = sk.muat()["smpn7uji"]
    assert s["status"] == "aktif" and s["maks_siswa"] == 800 and s["pendaftar"]["wa"] == "6281299990000"
    html = c.get("/vendor/").get_data(as_text=True)
    assert "SMP Negeri 7 Uji" in html and "Berlangganan" in html
    # perpanjang + catat pembayaran
    sampai_lama = s["sampai"]
    c.post("/vendor/sekolah/smpn7uji/perpanjang", data={
        "_csrf": t, "hari": "180", "maks_siswa": "1000", "nominal": "1.500.000",
        "catatan": "transfer BRI"})
    s = sk.muat()["smpn7uji"]
    assert s["sampai"] > sampai_lama and s["maks_siswa"] == 1000
    assert s["pembayaran"][-1]["nominal"] == 1500000
    html = c.get("/vendor/sekolah/smpn7uji").get_data(as_text=True)
    assert "Rp1.500.000" in html and "transfer BRI" in html and "wa.me/6281299990000" in html
    v_json = json.loads(open(f"{sk.ROOT}/smpn7uji/data/_vendor.json").read())
    assert v_json["berlaku_sampai"] == s["sampai"] and v_json["wa_vendor"] == "6285711112222"
    # sampai tanggal tertentu
    c.post("/vendor/sekolah/smpn7uji/perpanjang", data={"_csrf": t, "hari": "tanggal",
                                                        "sampai": "2032-06-30"})
    assert sk.muat()["smpn7uji"]["sampai"] == "2032-06-30"
    # nonaktif / aktifkan
    c.post("/vendor/sekolah/smpn7uji/status", data={"_csrf": t, "aksi": "nonaktif"})
    assert sk.muat()["smpn7uji"]["status"] == "nonaktif"
    c.post("/vendor/sekolah/smpn7uji/status", data={"_csrf": t, "aksi": "aktifkan"})
    assert sk.muat()["smpn7uji"]["status"] == "aktif"
    # ringkasan untuk panel tidak memuat password database
    ring = open(f"{sk.ROOT}/_ringkasan.json").read()
    assert "db_pass" not in ring and s["db_pass"] not in ring
    # kode yang sudah dipakai ditolak
    r = c.post("/vendor/tambah", data={"_csrf": t, "kode": "smpn7uji", "wa": "0812", "password": "x"})
    assert "sudah dipakai" in r.get_data(as_text=True)
