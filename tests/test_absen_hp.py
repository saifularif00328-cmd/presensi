"""Tahap 3: metode absen (RFID/QR/HP), absen dari HP berbasis lokasi + foto bukti."""
import io
import os
from datetime import timedelta

from PIL import Image

from app import config, utils
from app.db import connect, set_setting
from app.services import absen_hp as svc

# Titik sekolah uji (Monas) dan titik ±50 m / ±500 m darinya
SEK = (-6.175392, 106.827153)
DEKAT = (-6.175392 + 0.00045, 106.827153)     # ±50 m
JAUH = (-6.175392 + 0.0045, 106.827153)       # ±500 m
HP_A = "a" * 48
HP_B = "b" * 48


def _foto(ukuran=(480, 640)):
    b = io.BytesIO()
    Image.new("RGB", ukuran, (200, 160, 120)).save(b, "JPEG")
    b.seek(0)
    return b


def _sql(app, sql, args=()):
    with app.app_context():
        db = connect()
        db.execute(sql, args)
        db.commit()
        db.close()


def _baris(app, sql, args=()):
    with app.app_context():
        db = connect()
        r = db.execute(sql, args).fetchall()
        db.close()
    return r


def _siapkan(app, client, hp="1"):
    with app.app_context():
        db = connect()
        set_setting("metode_hp", hp, db=db)
        db.close()
    client.post("/sistem/metode-absen", data={"aksi": "lokasi", "nama": "Sekolah", "jenis": "sekolah",
                                              "lat": str(SEK[0]), "lng": str(SEK[1]), "radius": "100",
                                              "aktif": "1"})


def _masuk_siswa(app, sid):
    _sql(app, "UPDATE siswa SET pin_wajib_ganti = 0 WHERE id = ?", (sid,))
    c = app.test_client()
    with c.session_transaction() as s:
        s["portal"] = {"jenis": "siswa", "siswa_id": sid}
    return c


def _absen(c, titik=DEKAT, akurasi=15, hp=HP_A, foto=True, umur=1000, token=None):
    if token is None:
        r = c.post("/portal/absen/token", headers={"Accept": "application/json"})
        assert r.status_code == 200, r.get_data(as_text=True)
        token = r.get_json()["token"]
    data = {"token": token, "lat": str(titik[0]), "lng": str(titik[1]), "akurasi": str(akurasi),
            "umur_gps": str(umur), "perangkat": hp}
    if foto:
        data["foto"] = (_foto(), "foto.jpg")
    return c.post("/portal/absen/kirim", data=data, content_type="multipart/form-data").get_json()


def test_jarak_meter():
    assert utils.jarak_meter(*SEK, *SEK) == 0
    assert 45 < utils.jarak_meter(*SEK, *DEKAT) < 55
    assert 480 < utils.jarak_meter(*SEK, *JAUH) < 520


def test_metode_nonaktif_menolak_rfid_dan_qr(app, client, seed):
    client.post("/sistem/metode-absen", data={"aksi": "metode", "metode_rfid": "1"})
    r = client.post("/presensi/api/scan", json={"code": seed["ahmad"]["qr"]})
    j = r.get_json()
    assert not j["ok"] and "scan QR dinonaktifkan" in j["pesan"]
    # semua dimatikan -> QR tetap dinyalakan
    r = client.post("/sistem/metode-absen", data={"aksi": "metode"}, follow_redirects=True)
    assert "Minimal satu metode" in r.get_data(as_text=True)
    assert client.post("/presensi/api/scan", json={"code": seed["ahmad"]["qr"]}).get_json()["ok"]


def test_absen_hp_berhasil_dan_ditolak(app, client, seed, clock):
    sid = seed["ahmad"]["id"]
    c = _masuk_siswa(app, sid)
    # metode HP belum aktif
    assert "tidak diaktifkan" in c.get("/portal/absen").get_data(as_text=True)
    assert c.post("/portal/absen/token").status_code == 403
    _siapkan(app, client)
    h = c.get("/portal/absen").get_data(as_text=True)
    assert "Mulai absen" in h and "Sekolah" in h
    assert "Absen dari HP" in c.get(f"/portal/siswa/{sid}").get_data(as_text=True)

    j = _absen(c, titik=JAUH)
    assert not j["ok"] and "di luar area" in j["pesan"]
    j = _absen(c, akurasi=300)
    assert not j["ok"] and "kurang akurat" in j["pesan"]
    j = _absen(c, foto=False)
    assert not j["ok"] and "Foto selfie wajib" in j["pesan"]
    j = _absen(c)
    assert j["ok"] and j["jenis"] == "masuk" and j["lokasi"] == "Sekolah" and 40 < j["jarak"] < 60
    p = _baris(app, "SELECT * FROM presensi WHERE siswa_id = ?", (sid,))
    assert len(p) == 1 and p[0]["gerbang_masuk"] == "HP · Sekolah"
    a = _baris(app, "SELECT * FROM absen_hp WHERE status = 'ok'")[0]
    assert a["foto"] and os.path.exists(os.path.join(config.UPLOAD_DIR, a["foto"]))
    assert a["periksa"] == 1 and "HP baru" in a["alasan_periksa"]   # pendaftaran HP pertama
    assert len(_baris(app, "SELECT * FROM absen_hp WHERE status = 'ditolak'")) == 3


def test_token_sekali_pakai_dan_kedaluwarsa(app, client, seed, clock):
    _siapkan(app, client)
    c = _masuk_siswa(app, seed["ahmad"]["id"])
    t = c.post("/portal/absen/token").get_json()["token"]
    assert _absen(c, token=t)["ok"]
    j = _absen(c, token=t)
    assert not j["ok"] and "kedaluwarsa" in j["pesan"]
    t = c.post("/portal/absen/token").get_json()["token"]
    clock.value += timedelta(seconds=svc.TOKEN_DETIK + 5)
    assert "kedaluwarsa" in _absen(c, token=t)["pesan"]
    # token siswa lain tidak berlaku
    c2 = _masuk_siswa(app, seed["siti"]["id"])
    t = c.post("/portal/absen/token").get_json()["token"]
    assert "kedaluwarsa" in _absen(c2, token=t, hp=HP_B)["pesan"]


def test_satu_hp_satu_siswa_dan_reset(app, client, seed, clock):
    _siapkan(app, client)
    a, s = seed["ahmad"]["id"], seed["siti"]["id"]
    ca, cs = _masuk_siswa(app, a), _masuk_siswa(app, s)
    assert _absen(ca, hp=HP_A)["ok"]
    j = _absen(cs, hp=HP_A)                       # titip absen pakai HP teman
    assert not j["ok"] and "siswa lain" in j["pesan"]
    clock.set(15, 30)
    j = _absen(ca, hp=HP_B)                       # akun dipakai di HP lain
    assert not j["ok"] and "HP lain" in j["pesan"]
    h = client.get("/sistem/metode-absen").get_data(as_text=True)
    assert "Ahmad Fauzi" in h
    client.post("/sistem/metode-absen", data={"aksi": "reset_hp", "siswa_id": str(a)})
    j = _absen(ca, hp=HP_B)
    assert j["ok"] and j["jenis"] == "pulang"


def test_orang_tua_tidak_bisa_absen_hp(app, client, seed):
    _siapkan(app, client)
    c = app.test_client()
    with c.session_transaction() as s:
        s["portal"] = {"jenis": "ortu", "nomor": "6281234567890"}
    assert c.get("/portal/absen").status_code == 403
    assert c.post("/portal/absen/token").status_code == 403


def test_cakupan_kelas_dan_lokasi_kegiatan(app, client, seed, clock):
    _siapkan(app, client)
    # hanya kelas 8A (id 2) yang boleh
    client.post("/sistem/metode-absen", data={"aksi": "metode", "metode_qr": "1", "metode_hp": "1",
                                              "hp_cakupan": "kelas", "hp_kelas": ["2"],
                                              "hp_akurasi_maks": "100", "hp_foto_hari": "30"})
    ca = _masuk_siswa(app, seed["ahmad"]["id"])     # kelas 7A
    assert "belum diizinkan" in ca.get("/portal/absen").get_data(as_text=True)
    cb = _masuk_siswa(app, seed["budi"]["id"])      # kelas 8A
    assert "Mulai absen" in cb.get("/portal/absen").get_data(as_text=True)

    # lokasi PKL khusus Ahmad (NIS) selama seminggu -> Ahmad boleh walau kelasnya tidak
    _sql(app, "UPDATE siswa SET nis = '7001' WHERE id = ?", (seed["ahmad"]["id"],))
    pkl = (-6.2, 106.8)
    hari = utils.today()
    client.post("/sistem/metode-absen", data={
        "aksi": "lokasi", "nama": "PKL Bengkel", "jenis": "kegiatan", "lat": str(pkl[0]),
        "lng": str(pkl[1]), "radius": "150", "mulai": hari.isoformat(),
        "selesai": (hari + timedelta(days=6)).isoformat(), "siswa_nis": "7001, 9999", "aktif": "1"})
    assert "Mulai absen" in ca.get("/portal/absen").get_data(as_text=True)
    j = _absen(ca, titik=pkl)
    assert j["ok"] and j["lokasi"] == "PKL Bengkel"
    # di luar tanggal kegiatan tidak berlaku
    with app.app_context():
        db = connect()
        s = svc.siswa_lengkap(seed["ahmad"]["id"], db)
        nama = [r["nama"] for r in svc.lokasi_berlaku(s, hari + timedelta(days=10), db)]
        assert nama == ["Sekolah"]
        s = svc.siswa_lengkap(seed["siti"]["id"], db)
        assert [r["nama"] for r in svc.lokasi_berlaku(s, hari, db)] == ["Sekolah"]
        db.close()


def test_tanda_periksa_batal_dan_log(app, client, seed, clock):
    _siapkan(app, client)
    sid = seed["ahmad"]["id"]
    c = _masuk_siswa(app, sid)
    _absen(c)                                       # daftar HP (ditandai HP baru)
    _sql(app, "UPDATE absen_hp SET diperiksa = 1")
    clock.set(15, 30)
    titik_tepi = (SEK[0] + 0.00080, SEK[1])         # ±89 m dari radius 100 m
    j = _absen(c, titik=titik_tepi, akurasi=70, umur=90_000)
    assert j["ok"] and j["jenis"] == "pulang"
    a = _baris(app, "SELECT * FROM absen_hp WHERE jenis = 'pulang'")[0]
    assert a["periksa"] == 1
    for kata in ("kurang akurat", "tepi area", "90 detik"):
        assert kata in a["alasan_periksa"]

    h = client.get(f"/presensi/absen-hp?tanggal={utils.today_str()}&saring=periksa").get_data(as_text=True)
    assert "Ahmad Fauzi" in h and "Perlu diperiksa" in h
    masuk = _baris(app, "SELECT id FROM absen_hp WHERE jenis = 'masuk'")[0]["id"]
    r = client.post("/presensi/absen-hp", data={"aksi": "batal", "id": str(masuk)}, follow_redirects=True)
    assert "pulangnya dulu" in r.get_data(as_text=True)
    client.post("/presensi/absen-hp", data={"aksi": "batal", "id": str(a["id"])})
    p = _baris(app, "SELECT * FROM presensi WHERE siswa_id = ?", (sid,))[0]
    assert p["jam_pulang"] is None
    client.post("/presensi/absen-hp", data={"aksi": "batal", "id": str(masuk)})
    assert _baris(app, "SELECT * FROM presensi WHERE siswa_id = ?", (sid,)) == []
    assert len(_baris(app, "SELECT * FROM absen_hp WHERE status = 'batal'")) == 2
    log = _baris(app, "SELECT pesan FROM scan_log WHERE metode = 'hp' AND jenis = 'peringatan'")
    assert len(log) == 2 and "dibatalkan oleh" in log[0]["pesan"]


def test_bersihkan_foto_lama(app, client, seed, clock):
    _siapkan(app, client)
    c = _masuk_siswa(app, seed["ahmad"]["id"])
    assert _absen(c)["ok"]
    foto = _baris(app, "SELECT foto FROM absen_hp WHERE foto IS NOT NULL")[0]["foto"]
    path = os.path.join(config.UPLOAD_DIR, foto)
    assert os.path.exists(path)
    with app.app_context():
        db = connect()
        assert svc.bersihkan_foto(db) == 0
        clock.value += timedelta(days=31)
        assert svc.bersihkan_foto(db) == 1
        db.close()
    assert not os.path.exists(path)
    assert _baris(app, "SELECT foto FROM absen_hp")[0]["foto"] is None


def test_halaman_admin_dan_izin_akses(app, client, seed):
    h = client.get("/sistem/metode-absen").get_data(as_text=True)
    assert "Metode Absen" in h and "leaflet" in h.lower()
    assert client.get("/presensi/absen-hp").status_code == 200
    r = client.post("/sistem/metode-absen", data={"aksi": "lokasi", "nama": "X", "lat": "abc", "lng": "1"},
                    follow_redirects=True)
    assert "koordinat yang benar" in r.get_data(as_text=True)
    assert "geolocation=(self)" in client.get("/").headers.get("Permissions-Policy", "")


def test_halaman_scan_menampilkan_metode_nonaktif(app, client):
    assert "Dinonaktifkan sekolah" not in client.get("/presensi/scan").get_data(as_text=True)
    client.post("/sistem/metode-absen", data={"aksi": "metode", "metode_qr": "1"})
    assert "Dinonaktifkan sekolah: kartu RFID" in client.get("/presensi/scan").get_data(as_text=True)
