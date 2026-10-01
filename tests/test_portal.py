"""Portal Siswa & Orang Tua: login OTP WhatsApp, NIS + PIN, akses data anak sendiri, izin."""
import re

from app.db import connect, set_setting
from app.services import notify


def _tangkap_wa(monkeypatch):
    terkirim = []

    def fake_send(token, nomor, pesan):
        terkirim.append((nomor, pesan))
        return True, None
    monkeypatch.setattr(notify, "send_one", fake_send)
    monkeypatch.setattr(notify, "fonnte_token", lambda db=None: "tok")
    return terkirim


def test_portal_orang_tua_otp_dan_izin(app, client, seed, clock, monkeypatch):
    wa = _tangkap_wa(monkeypatch)
    ortu = app.test_client()
    assert ortu.get("/portal/").status_code == 302  # belum login
    # nomor tidak terdaftar: pesan sama (tidak membocorkan), tidak ada WA terkirim
    r = ortu.post("/portal/masuk", data={"aksi": "otp", "nomor": "0899-0000-1111"})
    assert "Bila nomor terdaftar" in r.get_data(as_text=True) and not wa
    # nomor Ahmad (081234567890) ditulis dengan format lain
    r = ortu.post("/portal/masuk", data={"aksi": "otp", "nomor": "+62 812-3456-7890"})
    assert wa and wa[-1][0] == "6281234567890"
    kode = re.search(r"\*(\d{8})\*", wa[-1][1]).group(1)
    r = ortu.post("/portal/masuk", data={"aksi": "verifikasi", "nomor": "081234567890",
                                         "kode": "00000000" if kode != "00000000" else "11111111"})
    assert "Kode salah" in r.get_data(as_text=True)
    r = ortu.post("/portal/masuk", data={"aksi": "verifikasi", "nomor": "081234567890",
                                         "kode": kode})
    assert r.status_code == 302
    # satu anak -> langsung ke halaman anak
    r = ortu.get("/portal/", follow_redirects=True)
    h = r.get_data(as_text=True)
    assert "Ahmad Fauzi" in h and "Hari ini" in h
    # kode OTP tidak bisa dipakai dua kali
    c2 = app.test_client()
    r = c2.post("/portal/masuk", data={"aksi": "verifikasi", "nomor": "081234567890", "kode": kode})
    assert r.status_code == 200 and "kedaluwarsa" in r.get_data(as_text=True)
    # tidak bisa membuka data siswa lain
    assert ortu.get(f"/portal/siswa/{seed['siti']['id']}").status_code == 404
    assert ortu.get(f"/portal/siswa/{seed['siti']['id']}/izin").status_code == 404
    # ajukan izin sakit -> masuk menu Perizinan sekolah
    r = ortu.post(f"/portal/siswa/{seed['ahmad']['id']}/izin",
                  data={"jenis": "Sakit", "tanggal_mulai": "2030-01-08",
                        "tanggal_selesai": "2030-01-09", "alasan": "Demam"})
    assert r.status_code == 302
    h = client.get("/perizinan/izin").get_data(as_text=True)
    assert "Demam" in h and "Orang tua (portal) 6281234567890" in h
    h = ortu.get(f"/portal/siswa/{seed['ahmad']['id']}").get_data(as_text=True)
    assert "Menunggu" in h and "Demam" in h


def test_portal_batas_kirim_otp(app, seed, clock, monkeypatch):
    wa = _tangkap_wa(monkeypatch)
    c = app.test_client()
    for _ in range(3):
        c.post("/portal/masuk", data={"aksi": "otp", "nomor": "081234567890"})
    r = c.post("/portal/masuk", data={"aksi": "otp", "nomor": "081234567890"})
    assert "Terlalu sering" in r.get_data(as_text=True) and len(wa) == 3


def test_portal_siswa_nis_pin(app, client, seed, clock):
    with app.app_context():
        db = connect()
        db.execute("UPDATE siswa SET nis = '2001' WHERE id = ?", (seed["siti"]["id"],))
        db.commit()
        db.close()
    r = client.post("/master/pin", data={"kelas_id": "1", "siswa_id": [str(seed["siti"]["id"])]})
    h = r.get_data(as_text=True)
    pin = re.search(r'class="pin">(\d{6})<', h).group(1)
    assert "Siti Aminah" in h and "/portal/masuk" in h
    s = app.test_client()
    r = s.post("/portal/masuk", data={"aksi": "siswa", "nis": "2001", "pin": pin})
    assert r.status_code == 302
    # wajib ganti PIN dulu
    r = s.get("/portal/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/portal/ganti-pin")
    assert "terlalu mudah" in s.post("/portal/ganti-pin", data={"pin": "111111", "ulang": "111111"}) \
        .get_data(as_text=True)
    s.post("/portal/ganti-pin", data={"pin": "482913", "ulang": "482913"})
    h = s.get("/portal/", follow_redirects=True).get_data(as_text=True)
    assert "Siti Aminah" in h and "Ajukan" not in h  # siswa tidak bisa mengajukan izin
    assert s.get(f"/portal/siswa/{seed['siti']['id']}/izin").status_code == 403
    assert s.get(f"/portal/siswa/{seed['ahmad']['id']}").status_code == 404
    # PIN salah berkali-kali -> dikunci sementara
    t = app.test_client()
    for _ in range(5):
        t.post("/portal/masuk", data={"aksi": "siswa", "nis": "2001", "pin": "000000"})
    r = t.post("/portal/masuk", data={"aksi": "siswa", "nis": "2001", "pin": "482913"})
    assert "Terlalu banyak" in r.get_data(as_text=True)


def test_portal_bisa_dimatikan_dan_pwa(app, client):
    c = app.test_client()
    assert c.get("/portal/manifest.webmanifest").get_json()["display"] == "standalone"
    assert c.get("/portal/sw.js").status_code == 200
    r = c.get("/portal/ikon-512.png")
    assert r.status_code == 200 and r.data[:8] == b"\x89PNG\r\n\x1a\n"
    with app.app_context():
        set_setting("portal_aktif", "0", db=connect())
    assert c.get("/portal/masuk").status_code == 503
