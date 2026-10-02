"""Tahap 2 — gerbang, Presensiku Pos (API), penjaga scan ganda, layar gerbang."""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime as dt

from app import utils
from app.db import connect, set_setting


def kirim(client, kode, rahasia, path, body, waktu=None, nonce=None):
    raw = json.dumps(body).encode()
    waktu = str(int(waktu if waktu is not None else time.time()))
    nonce = nonce or secrets.token_hex(8)
    sig = hmac.new(rahasia.encode(), f"{kode}\n{waktu}\n{nonce}\n".encode() + raw,
                   hashlib.sha256).hexdigest()
    return client.post(path, data=raw, content_type="application/json",
                       headers={"X-Pos": kode, "X-Waktu": waktu, "X-Nonce": nonce, "X-Tanda": sig,
                                "X-Versi": "1.0.0"})


def _db(app, sql, args=(), satu=True):
    with app.app_context():
        db = connect()
        cur = db.execute(sql, args)
        r = cur.fetchone() if satu else cur.fetchall()
        db.close()
    return r


def _siapkan(app, client):
    """Dua gerbang + satu Pos yang sudah dipasangkan. Mengembalikan (anon, kode, rahasia, gerbang)."""
    client.post("/sistem/perangkat-scan", data={"aksi": "gerbang_simpan", "nama": "Gerbang Depan",
                                                "mode": "auto", "urutan": "1"})
    client.post("/sistem/perangkat-scan", data={"aksi": "gerbang_simpan", "nama": "Gerbang Belakang",
                                                "mode": "masuk", "urutan": "2"})
    r = client.post("/sistem/perangkat-scan", data={"aksi": "pos_tambah", "nama": "PC Satpam"})
    assert r.status_code == 302
    p = _db(app, "SELECT * FROM pos ORDER BY id DESC LIMIT 1")
    html = client.get(r.headers["Location"]).get_data(as_text=True)
    assert p["kode_pasang"] in html                       # kode pasang tampil untuk admin
    anon = app.test_client()
    # kode salah ditolak, kode benar sekali pakai
    assert anon.post("/api/pos/pasang", json={"kode_pasang": "AAAA-AAAA"}).status_code == 403
    j = anon.post("/api/pos/pasang", json={"kode_pasang": p["kode_pasang"].replace("-", "").lower(),
                                           "versi": "1.0.0"}).get_json()
    assert j["ok"] and j["kode"] == p["kode"] and j["rahasia"] == p["rahasia"]
    assert anon.post("/api/pos/pasang", json={"kode_pasang": p["kode_pasang"]}).status_code == 403
    g = {r["nama"]: r["id"] for r in _db(app, "SELECT id, nama FROM gerbang", satu=False)}
    return anon, j["kode"], j["rahasia"], g


def test_pos_pasang_sinkron_scan(app, client, seed, clock):
    anon, kode, rahasia, g = _siapkan(app, client)
    # sinkron melaporkan dua scanner terdeteksi; belum ada gerbangnya
    k = kirim(anon, kode, rahasia, "/api/pos/sinkron", {"antrean": 2, "scanner": [
        {"kunci": "HID#VID_1EAB&PID_1D06#A", "jenis": "keyboard", "label": "Netum USB"},
        {"kunci": "COM5", "jenis": "com", "label": "COM5 - Honeywell"}]}).get_json()
    assert k["ok"] and k["qr_secret"] and [x["nama"] for x in k["gerbang"]] == ["Gerbang Depan",
                                                                                 "Gerbang Belakang"]
    assert {s["kunci"] for s in k["scanner"]} == {"HID#VID_1EAB&PID_1D06#A", "COM5"}
    assert _db(app, "SELECT antrean FROM pos")["antrean"] == 2
    # scan dari scanner yang belum dipetakan: ditolak & tidak disimpan
    h = kirim(anon, kode, rahasia, "/api/pos/scan", {"scans": [
        {"uuid": "u1", "kode": seed["ahmad"]["qr"], "kunci": "HID#VID_1EAB&PID_1D06#A"}]}).get_json()
    assert h["hasil"][0]["error"] == "scanner"
    assert _db(app, "SELECT COUNT(*) AS n FROM pos_scan")["n"] == 0
    # petugas memilih gerbang di layar Pos
    kirim(anon, kode, rahasia, "/api/pos/scanner", {"kunci": "HID#VID_1EAB&PID_1D06#A",
                                                     "jenis": "keyboard", "label": "Netum USB",
                                                     "gerbang_id": g["Gerbang Depan"]})
    kirim(anon, kode, rahasia, "/api/pos/scanner", {"kunci": "COM5", "jenis": "com",
                                                     "gerbang_id": g["Gerbang Belakang"]})
    # dua scanner bersamaan, termasuk satu scan tertunda (offline) jam 06:40
    ts = int(dt(2030, 1, 7, 6, 40, tzinfo=utils.zona()).timestamp())
    real = time.time()
    h = kirim(anon, kode, rahasia, "/api/pos/scan", {"scans": [
        {"uuid": "u1", "kode": seed["ahmad"]["qr"], "kunci": "HID#VID_1EAB&PID_1D06#A", "ts": ts},
        {"uuid": "u2", "kode": seed["siti"]["qr"], "kunci": "COM5"},
        {"uuid": "u3", "kode": "PSD1.PALSU.XXXX", "kunci": "COM5"}]}, waktu=real).get_json()["hasil"]
    assert [x["uuid"] for x in h] == ["u1", "u2", "u3"]
    assert h[0]["ok"] and h[0]["jam"] == "06:40" and h[0]["gerbang"] == "Gerbang Depan"
    assert h[1]["ok"] and h[1]["gerbang"] == "Gerbang Belakang"
    assert not h[2]["ok"] and h[2]["level"] == "error"
    r = _db(app, "SELECT jam_masuk, gerbang_masuk FROM presensi WHERE siswa_id = ?",
            (seed["ahmad"]["id"],))
    assert r["jam_masuk"] == "06:40:00" and r["gerbang_masuk"] == "Gerbang Depan"
    # kiriman ulang uuid yang sama (koneksi putus sebelum balasan) tidak dicatat dua kali
    h2 = kirim(anon, kode, rahasia, "/api/pos/scan", {"scans": [
        {"uuid": "u1", "kode": seed["ahmad"]["qr"], "kunci": "HID#VID_1EAB&PID_1D06#A"}]}).get_json()
    assert h2["hasil"][0]["ulang"] and h2["hasil"][0]["jam"] == "06:40"
    assert _db(app, "SELECT COUNT(*) AS n FROM scan_log WHERE siswa_id = ?",
               (seed["ahmad"]["id"],))["n"] == 1
    # data siswa untuk offline + versi
    s = kirim(anon, kode, rahasia, "/api/pos/siswa", {}).get_json()
    assert len(s["siswa"]) == 3 and {"qr_token", "rfid_uid", "kelas"} <= set(s["siswa"][0])
    assert kirim(anon, kode, rahasia, "/api/pos/siswa", {"versi": s["versi"]}).get_json()["sama"]
    # admin melihat scanner + gerbang; tanda tangan salah ditolak
    html = client.get("/sistem/perangkat-scan").get_data(as_text=True)
    assert "Netum USB" in html and "COM5 - Honeywell" in html
    assert kirim(anon, kode, "salah", "/api/pos/sinkron", {}).status_code == 401
    # rekap: kolom & filter gerbang
    rek = client.get("/presensi/rekap?gerbang=Gerbang+Belakang").get_data(as_text=True)
    assert "Siti Aminah" in rek and "Ahmad Fauzi" not in rek


def test_pos_pasang_ulang_memutus_pc_lama(app, client, seed):
    anon, kode, rahasia, _ = _siapkan(app, client)
    pid = _db(app, "SELECT id FROM pos")["id"]
    client.post("/sistem/perangkat-scan", data={"aksi": "pos_pasang_ulang", "pos_id": pid})
    assert kirim(anon, kode, rahasia, "/api/pos/sinkron", {}).status_code == 401
    # kode pasang salah berkali-kali dikunci
    for _ in range(25):
        r = anon.post("/api/pos/pasang", json={"kode_pasang": "ZZZZ-ZZZZ"})
    assert r.status_code == 429


def test_scan_ganda_lintas_gerbang(app, client, seed, clock):
    clock.set(6, 45)
    r1 = client.post("/presensi/api/scan", json={"code": seed["budi"]["qr"]}).get_json()
    assert r1["ok"] and r1["jenis"] == "masuk"
    clock.set(6, 45)
    clock.value = clock.value.replace(second=30)
    r2 = client.post("/presensi/api/scan", json={"code": seed["budi"]["qr"]}).get_json()
    assert r2["ok"] and r2["jenis"] == "ganda" and r2["level"] == "info"
    assert _db(app, "SELECT COUNT(*) AS n FROM scan_log WHERE siswa_id = ?",
               (seed["budi"]["id"],))["n"] == 1
    clock.set(6, 50)                                       # lewat 60 detik: peringatan biasa
    r3 = client.post("/presensi/api/scan", json={"code": seed["budi"]["qr"]}).get_json()
    assert not r3["ok"] and r3["level"] == "warning"
    with app.app_context():
        db = connect()
        set_setting("scan_jeda_ganda", "0", db=db)
        db.close()
    clock.value = clock.value.replace(second=10)
    assert client.post("/presensi/api/scan", json={"code": seed["budi"]["qr"]}).get_json()["level"] == "warning"


def test_layar_gerbang_server(app, client, seed, clock):
    client.post("/sistem/perangkat-scan", data={"aksi": "gerbang_simpan", "nama": "Gerbang Depan",
                                                "mode": "auto"})
    gid = _db(app, "SELECT id FROM gerbang")["id"]
    client.post("/sistem/perangkat", data={"nama": "ESP Depan", "mode": "auto", "aktif": "1",
                                           "gerbang_id": gid})
    p = _db(app, "SELECT kode, rahasia FROM perangkat")
    client.post("/master/rfid/pasang", json={"siswa_id": seed["budi"]["id"], "uid": "04A1B2C3"})
    anon = app.test_client()
    raw = json.dumps({"uid": "04A1B2C3"}).encode()
    w, n = str(int(time.time())), "n1"
    sig = hmac.new(p["rahasia"].encode(), f"{p['kode']}\n{w}\n{n}\n".encode() + raw,
                   hashlib.sha256).hexdigest()
    anon.post("/api/perangkat/tap", data=raw, content_type="application/json",
              headers={"X-Perangkat": p["kode"], "X-Waktu": w, "X-Nonce": n, "X-Tanda": sig})
    assert "layar_gerbang.js" in client.get("/presensi/layar-gerbang").get_data(as_text=True)
    d = client.get("/presensi/api/layar").get_json()
    assert d["gerbang"] == ["Gerbang Depan"] and d["hadir"]["Gerbang Depan"] == 1
    it = d["item"][-1]
    assert it["gerbang"] == "Gerbang Depan" and it["siswa"]["nama"] == "Budi Santoso" and it["awal"]
    assert client.get(f"/presensi/api/layar?sejak={d['terakhir']}").get_json()["item"] == []
    # QR dari modul scanner QR di ESP32 (field "kode")
    raw = json.dumps({"kode": seed["siti"]["qr"]}).encode()
    sig = hmac.new(p["rahasia"].encode(), f"{p['kode']}\n{w}\nn2\n".encode() + raw,
                   hashlib.sha256).hexdigest()
    j = anon.post("/api/perangkat/tap", data=raw, content_type="application/json",
                  headers={"X-Perangkat": p["kode"], "X-Waktu": w, "X-Nonce": "n2",
                           "X-Tanda": sig}).get_json()
    assert j["ok"] and j["nama"] == "Siti Aminah"
    assert _db(app, "SELECT metode FROM scan_log ORDER BY id DESC LIMIT 1")["metode"] == "qr"
