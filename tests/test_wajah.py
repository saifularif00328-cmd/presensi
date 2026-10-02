"""Tahap 4: pencocokan wajah untuk absen HP (persetujuan ortu, data terenkripsi, tantangan tengok)."""
import io
import os
import threading

import pytest
from PIL import Image

from app import config
from app.db import connect, set_setting
from app.services import absen_hp, wajah

from .test_absen_hp import DEKAT, HP_A, _baris, _masuk_siswa, _siapkan, _sql

# "Gambar" uji = JPEG warna polos; mesin palsu menerjemahkan warna -> hasil deteksi.
A_LURUS, A_KIRI, A_KANAN, ORANG_B, TANPA_WAJAH, BURAM, ACUAN = (
    (200, 0, 0), (200, 100, 0), (200, 0, 100), (0, 0, 200), (10, 10, 10), (90, 90, 90), (250, 250, 0))
EMB_A = [1.0] + [0.0] * 127
EMB_A2 = [0.95, 0.31] + [0.0] * 126      # orang sama, foto lain (kemiripan ±0,95)
EMB_B = [0.0, 0.0, 1.0] + [0.0] * 125


def _jpg(warna):
    b = io.BytesIO()
    Image.new("RGB", (480, 640), warna).save(b, "JPEG", quality=95)
    return b.getvalue()


def _f(emb, yaw=0.0, tajam=120.0):
    return {"kotak": [140, 160, 200, 220], "skor": 0.93, "yaw": yaw, "tajam": tajam, "terang": 120.0,
            "embedding": emb}


def _palsu(data):
    w = Image.open(io.BytesIO(data)).convert("RGB").getpixel((5, 5))
    dekat = min((A_LURUS, A_KIRI, A_KANAN, ORANG_B, TANPA_WAJAH, BURAM, ACUAN),
                key=lambda c: sum((a - b) ** 2 for a, b in zip(c, w)))
    wajah_ = {A_LURUS: [_f(EMB_A2)], A_KIRI: [_f(EMB_A2, yaw=0.35)], A_KANAN: [_f(EMB_A2, yaw=-0.35)],
              ORANG_B: [_f(EMB_B)], TANPA_WAJAH: [], BURAM: [_f(EMB_A, tajam=5)], ACUAN: [_f(EMB_A)]}[dekat]
    return {"ok": True, "lebar": 480, "tinggi": 640, "wajah": wajah_}


@pytest.fixture
def mesin(monkeypatch):
    monkeypatch.setattr(wajah, "analisis_gambar", _palsu)
    monkeypatch.setattr(wajah, "buat_tantangan", lambda: "kiri")


def _foto_siswa(app, sid, warna=A_LURUS):
    nama = f"foto/siswa_{sid}_uji.jpg"
    os.makedirs(os.path.join(config.UPLOAD_DIR, "foto"), exist_ok=True)
    with open(os.path.join(config.UPLOAD_DIR, nama), "wb") as fh:
        Image.new("RGB", (480, 640), warna).save(fh, "JPEG", quality=95)
    _sql(app, "UPDATE siswa SET foto = ? WHERE id = ?", (nama, sid))


def _setel(app, **kv):
    with app.app_context():
        db = connect()
        for k, v in kv.items():
            set_setting(k, v, db=db)
        db.close()


def _daftar_wajah(app, client, sid):
    _foto_siswa(app, sid, ACUAN)           # foto acuan = EMB_A (lurus)
    client.post("/sistem/data-wajah", data={"aksi": "setuju", "siswa_id": [str(sid)], "kelas_id": "1"})
    client.post("/sistem/data-wajah", data={"aksi": "daftar_foto", "siswa_id": [str(sid)], "kelas_id": "1"})


def _absen_wajah(c, f1=A_LURUS, f2=A_KIRI, sumber="kamera"):
    t = c.post("/portal/absen/token", headers={"Accept": "application/json"}).get_json()
    data = {"token": t["token"], "lat": str(DEKAT[0]), "lng": str(DEKAT[1]), "akurasi": "10",
            "umur_gps": "500", "perangkat": HP_A, "sumber": sumber, "foto": (io.BytesIO(_jpg(f1)), "a.jpg")}
    if f2 is not None:
        data["foto2"] = (io.BytesIO(_jpg(f2)), "b.jpg")
    return t, c.post("/portal/absen/kirim", data=data, content_type="multipart/form-data").get_json()


def test_enkripsi_embedding_dan_kemiripan(app):
    with app.app_context():
        teks = wajah.enkode(EMB_A2)
        assert "0.95" not in teks and teks.startswith("gAAAA")        # Fernet
        hasil = wajah.dekode(teks)
        assert len(hasil) == 128 and abs(hasil[0] - 0.95) < 1e-6
    assert wajah.kemiripan(EMB_A, EMB_A2) > 0.9 and wajah.kemiripan(EMB_A, EMB_B) == 0


def test_kualitas_foto_acuan():
    assert wajah.wajah_utama({"ok": True, "wajah": []})[1] == "Wajah tidak terdeteksi"
    assert wajah.wajah_utama({"ok": True, "wajah": [_f(EMB_A, tajam=3)]})[1] == "Foto buram"
    assert "lebih dari satu" in wajah.wajah_utama({"ok": True, "wajah": [_f(EMB_A), _f(EMB_B)]})[1]
    assert "lurus" in wajah.wajah_utama({"ok": True, "wajah": [_f(EMB_A, yaw=0.4)]}, acuan=True)[1]
    assert wajah.wajah_utama({"ok": True, "wajah": [_f(EMB_A, yaw=0.4)]})[0] is not None


def test_data_wajah_butuh_persetujuan_dan_tersimpan_terenkripsi(app, client, seed, mesin):
    sid, siti = seed["ahmad"]["id"], seed["siti"]["id"]
    _foto_siswa(app, sid)
    _foto_siswa(app, siti, BURAM)
    r = client.post("/sistem/data-wajah", data={"aksi": "daftar_foto", "siswa_id": [str(sid)], "kelas_id": "1"},
                    follow_redirects=True)
    assert "persetujuan orang tua" in r.get_data(as_text=True)
    client.post("/sistem/data-wajah", data={"aksi": "setuju", "siswa_id": [str(sid), str(siti)], "kelas_id": "1"})
    r = client.post("/sistem/data-wajah", data={"aksi": "daftar_foto", "kelas_id": "1"}, follow_redirects=True)
    h = r.get_data(as_text=True)
    assert "1 data wajah dibuat" in h and "Siti Aminah: Foto buram" in h
    w = _baris(app, "SELECT * FROM wajah_siswa WHERE siswa_id = ?", (sid,))[0]
    assert w["status"] == "siap" and w["setuju"] == 1 and "formulir kertas" in w["setuju_oleh"]
    assert w["embedding"].startswith("gAAAA")
    assert _baris(app, "SELECT status FROM wajah_siswa WHERE siswa_id = ?", (siti,))[0]["status"] == "ulang"
    h = client.get("/sistem/data-wajah?kelas_id=1").get_data(as_text=True)
    assert "perlu foto ulang" in h and "Data Wajah" in h
    # rekam ulang lewat kamera
    r = client.post("/sistem/data-wajah", data={"aksi": "rekam", "siswa_id": str(siti), "kelas_id": "1",
                                               "foto": (io.BytesIO(_jpg(A_LURUS)), "w.jpg")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "Data wajah tersimpan" in r.get_data(as_text=True)
    # cabut -> embedding hilang
    client.post("/sistem/data-wajah", data={"aksi": "cabut", "siswa_id": str(sid), "kelas_id": "1"})
    w = _baris(app, "SELECT * FROM wajah_siswa WHERE siswa_id = ?", (sid,))[0]
    assert w["setuju"] == 0 and w["embedding"] is None and w["setuju_oleh"].startswith("dicabut")
    h = client.get("/sistem/data-wajah/formulir?kelas_id=1").get_data(as_text=True)
    assert "PERSETUJUAN PENGGUNAAN DATA WAJAH" in h and "Ahmad Fauzi" in h and "Siti Aminah" in h


def test_persetujuan_orang_tua_lewat_portal(app, client, seed, mesin):
    sid = seed["ahmad"]["id"]
    _siapkan(app, client)
    _setel(app, hp_wajah="tandai")
    _foto_siswa(app, sid)
    ortu = app.test_client()
    with ortu.session_transaction() as s:
        s["portal"] = {"jenis": "ortu", "nomor": "6281234567890"}
    h = ortu.get(f"/portal/siswa/{sid}").get_data(as_text=True)
    assert "Persetujuan data wajah" in h and "Saya setuju" in h
    ortu.post(f"/portal/siswa/{sid}/wajah", data={"setuju": "1"})
    w = _baris(app, "SELECT * FROM wajah_siswa WHERE siswa_id = ?", (sid,))[0]
    assert w["setuju"] == 1 and w["status"] == "siap" and "Orang tua (portal) 6281234567890" in w["setuju_oleh"]
    assert ortu.post(f"/portal/siswa/{seed['budi']['id']}/wajah", data={"setuju": "1"}).status_code == 404
    siswa = _masuk_siswa(app, sid)
    assert siswa.post(f"/portal/siswa/{sid}/wajah", data={"setuju": "0"}).status_code == 403
    ortu.post(f"/portal/siswa/{sid}/wajah", data={"setuju": "0"})
    assert _baris(app, "SELECT embedding FROM wajah_siswa WHERE siswa_id = ?", (sid,))[0]["embedding"] is None


def test_absen_hp_wajib_wajah(app, client, seed, clock, mesin):
    sid = seed["ahmad"]["id"]
    _siapkan(app, client)
    _setel(app, hp_wajah="wajib")
    c = _masuk_siswa(app, sid)
    assert "Data wajah Anda belum terdaftar" in c.get("/portal/absen").get_data(as_text=True)
    _daftar_wajah(app, client, sid)
    assert "menengok" in c.get("/portal/absen").get_data(as_text=True)

    t, j = _absen_wajah(c, f1=ORANG_B)
    assert t["tantangan"] == "kiri"
    assert not j["ok"] and "Wajah tidak cocok" in j["pesan"]
    _, j = _absen_wajah(c, f2=A_KANAN)                       # tengok ke arah yang salah
    assert not j["ok"] and "Tidak menengok ke kiri" in j["pesan"]
    _, j = _absen_wajah(c, f2=None)
    assert not j["ok"] and "tantangan" in j["pesan"]
    _, j = _absen_wajah(c, f1=TANPA_WAJAH)
    assert not j["ok"] and "Wajah tidak terdeteksi" in j["pesan"]
    _, j = _absen_wajah(c)
    assert j["ok"] and j["jenis"] == "masuk"
    ok = _baris(app, "SELECT * FROM absen_hp WHERE status = 'ok'")[0]
    assert float(ok["skor_wajah"]) > 0.9
    tolak = _baris(app, "SELECT * FROM absen_hp WHERE status = 'ditolak' AND pesan LIKE 'Wajah tidak cocok%'")[0]
    assert tolak["foto"] and float(tolak["skor_wajah"]) < 0.1     # foto penyusup disimpan sebagai bukti
    h = client.get("/presensi/absen-hp").get_data(as_text=True)
    assert "wajah 0.95" in h
    # kamera bawaan HP (sumber berkas) bisa tercermin: arah apa pun asal benar-benar menengok
    clock.set(15, 30)
    _, j = _absen_wajah(c, f2=A_KANAN, sumber="berkas")
    assert j["ok"] and j["jenis"] == "pulang"


def test_absen_hp_mode_tandai_dan_mesin_mati(app, client, seed, clock, mesin, monkeypatch):
    sid = seed["ahmad"]["id"]
    _siapkan(app, client)
    _setel(app, hp_wajah="tandai", wajah_tantangan="0")
    c = _masuk_siswa(app, sid)
    t, j = _absen_wajah(c, f1=ORANG_B, f2=None)               # belum ada data wajah -> tetap boleh
    assert t["tantangan"] is None
    assert j["ok"]
    a = _baris(app, "SELECT * FROM absen_hp WHERE status = 'ok'")[0]
    assert a["periksa"] == 1 and "wajah: Data wajah siswa belum terdaftar" in a["alasan_periksa"]

    def mati(_data):
        raise wajah.TidakTersedia("uji")
    monkeypatch.setattr(wajah, "analisis_gambar", mati)
    _daftar_wajah(app, client, seed["siti"]["id"])            # gagal: mesin mati
    _setel(app, hp_wajah="wajib")
    clock.set(15, 30)
    _sql(app, "INSERT INTO wajah_siswa(siswa_id, setuju, status, embedding) VALUES (?, 1, 'siap', ?)",
         (sid, wajah.enkode(EMB_A)))
    _, j = _absen_wajah(c, f2=None)
    assert not j["ok"] and "pencocokan wajah sedang tidak tersedia" in j["pesan"]


def test_halaman_metode_menyimpan_pengaturan_wajah(app, client):
    client.post("/sistem/metode-absen", data={"aksi": "metode", "metode_qr": "1", "metode_hp": "1",
                                              "hp_cakupan": "semua", "hp_akurasi_maks": "100",
                                              "hp_foto_hari": "30", "hp_wajah": "wajib", "wajah_ambang": "0.9"})
    with app.app_context():
        from app.db import get_setting
        db = connect()
        assert get_setting("hp_wajah", db=db) == "wajib"
        assert get_setting("wajah_ambang", db=db) == "0.70"          # dibatasi
        assert get_setting("wajah_tantangan", db=db) == "0"
        db.close()
    assert "Pencocokan wajah" in client.get("/sistem/metode-absen").get_data(as_text=True)


def test_layanan_wajah_bersama(monkeypatch):
    from http.server import ThreadingHTTPServer

    from app import wajah_worker
    monkeypatch.setenv("PRESENSI_WAJAH_KUNCI", "rahasia-uji")
    monkeypatch.setattr(wajah_worker.mesin, "analisis", _palsu)
    monkeypatch.setattr(wajah_worker.mesin, "_muat", lambda: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), wajah_worker.Penangan)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("PRESENSI_WAJAH_URL", f"http://127.0.0.1:{srv.server_address[1]}")
        hasil = wajah.analisis_gambar(_jpg(A_KIRI))
        assert hasil["ok"] and hasil["wajah"][0]["yaw"] == 0.35
        assert wajah.status_mesin()[0]
        import requests
        url = os.environ["PRESENSI_WAJAH_URL"] + "/analisis"
        assert requests.post(url, data=_jpg(A_KIRI), headers={"X-Kunci": "salah"}).status_code == 403
        assert requests.post(url, data=_jpg(A_KIRI)).status_code == 403
    finally:
        srv.shutdown()
    with pytest.raises(wajah.TidakTersedia):
        wajah.analisis_gambar(_jpg(A_KIRI))                       # layanan sudah mati


UJI_DIR = os.environ.get("PRESENSI_UJI_WAJAH_DIR", "")


@pytest.mark.skipif(not os.path.exists(os.path.join(UJI_DIR, wajah.SFACE)),
                    reason="model & foto uji wajah tidak tersedia (set PRESENSI_UJI_WAJAH_DIR)")
def test_mesin_wajah_sungguhan():
    """Mesin asli: orang sama cocok, orang lain tidak, arah tengok (yaw) terbaca."""
    import cv2
    m = wajah.Mesin(UJI_DIR)
    baca = lambda n: open(os.path.join(UJI_DIR, n), "rb").read()  # noqa: E731
    lena = m.analisis(baca("lena.jpg"))
    f, alasan = wajah.wajah_utama(lena)
    assert f is not None, alasan
    img = cv2.imread(os.path.join(UJI_DIR, "lena.jpg"))
    gelap = cv2.convertScaleAbs(img[20:480, 30:500], alpha=0.8, beta=-10)
    f2 = wajah.wajah_utama(m.analisis(cv2.imencode(".jpg", gelap, [cv2.IMWRITE_JPEG_QUALITY, 50])[1].tobytes()))[0]
    cermin = wajah.wajah_utama(m.analisis(cv2.imencode(".jpg", cv2.flip(img, 1))[1].tobytes()))[0]
    messi = m.analisis(baca("messi5.jpg"))
    assert "terlalu kecil" in wajah.wajah_utama(messi)[1]            # wajah 30 px ditolak
    lain = messi["wajah"][0]
    buram = m.analisis(cv2.imencode(".jpg", cv2.GaussianBlur(img, (0, 0), 3))[1].tobytes())
    assert wajah.wajah_utama(buram, acuan=True)[1] == "Foto buram"
    assert wajah.kemiripan(f["embedding"], f2["embedding"]) > 0.6
    assert wajah.kemiripan(f["embedding"], lain["embedding"]) < 0.3
    assert f["yaw"] * cermin["yaw"] < 0                              # dicerminkan -> arah berlawanan
    assert absen_hp.TOKEN_DETIK >= 60
