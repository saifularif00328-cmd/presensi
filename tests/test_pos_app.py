"""Presensiku Pos (aplikasi Windows) — diuji di Linux dengan server sungguhan (Flask + MariaDB).

Bagian khusus Windows (Raw Input) diuji di tests/test_pos_windows.py pada runner Windows (CI).
"""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime as dt

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "pos"))

from presensiku_pos import data_siswa as DS  # noqa: E402
from presensiku_pos import masukan_serial, masukan_windows  # noqa: E402
from presensiku_pos.perakit import Perakit  # noqa: E402
from presensiku_pos.vk import karakter  # noqa: E402

from app import utils  # noqa: E402
from app.db import connect  # noqa: E402

SERVER = "http://pos.uji/smpn1"


# ------------------------------------------------------------------ adaptor HTTP -> Flask
class _Jawab:
    def __init__(self, r):
        self.status_code = r.status_code
        self.content = r.data

    def json(self):
        return json.loads(self.content)


class SesiFlask:
    """Pengganti requests.Session: meneruskan ke Flask test client; `putus` = internet mati."""

    def __init__(self, client):
        self.client = client
        self.putus = False

    def post(self, url, data=None, headers=None, timeout=None):
        import requests
        if self.putus:
            raise requests.ConnectionError("internet putus (uji)")
        assert url.startswith(SERVER)
        return _Jawab(self.client.post(url[len(SERVER):], data=data, headers=headers or {}))

    def get(self, url, timeout=None):
        return type("R", (), {"status_code": 404})()


# ------------------------------------------------------------------ unit
def test_pengenalan_kartu_sama_dengan_server():
    from app import qr, rfid
    for tok in ("ABCDEF0123456789", "00E6A4AAB790ABD1"):
        assert DS.checksum(tok, "rahasia-x") == qr._checksum(tok, "rahasia-x")
    for t in ("04A1B2C3", "04:a1:b2:c3", "2864561924", "1234", "ZZZZ", "0123456789ABCDEF01", ""):
        assert DS.looks_like_uid(t) == rfid.looks_like_uid(t)
        assert DS.uid_candidates(t) == rfid.candidates(t)


def test_vk_dan_perakit_banyak_alat_bersamaan():
    assert karakter(0x41) == "a" and karakter(0x41, True) == "A" and karakter(0xBE) == "."
    assert karakter(0x31, True) == "!" and karakter(0x63) == "3" and karakter(0x10) is None

    def ketik(teks):
        out = []
        for ch in teks:
            if ch.isalpha():
                out += [(0x10, True), (ord(ch.upper()), True), (ord(ch.upper()), False), (0x10, False)]
            elif ch == ".":
                out += [(0xBE, True), (0xBE, False)]
            else:
                out += [(ord(ch), True), (ord(ch), False)]
        return out + [(0x0D, True), (0x0D, False)]

    p = Perakit()
    kode = {"A": "PSD1.AB12.XY", "B": "04A1B2C3", "C": "PSD1.CD34.ZZ"}
    alur = {k: ketik(v) for k, v in kode.items()}
    hasil, t = [], 0.0
    while any(alur.values()):                     # tiga scanner mengetik selang-seling
        for k in "ABC":
            if alur[k]:
                vk, turun = alur[k].pop(0)
                t += 0.002
                s = p.tombol(k, vk, turun, t)
                if s:
                    hasil.append(s)
    assert {s.kunci: s.teks for s in hasil} == kode and all(s.cepat for s in hasil)
    # ketikan manusia (lambat) di keyboard biasa: bukan scan cepat
    t = 100.0
    lambat = []
    for vk, turun in ketik("1234"):
        t += 0.2
        lambat.append(p.tombol("K", vk, turun, t))
    s = [x for x in lambat if x][0]
    assert s.teks == "1234" and not s.cepat
    # scanner tanpa akhiran Enter
    for i, ch in enumerate("04A1B2C3"):
        p.tombol("D", ord(ch), True, 200 + i * 0.003)
    assert p.periksa_waktu(200.2)[0].teks.upper() == "04A1B2C3"


def test_kunci_alat_windows_stabil():
    j = r"\\?\HID#VID_1EAB&PID_1D06&MI_00#7&2a6d1b1&0&0000#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"
    k1, label = masukan_windows.kunci_dan_label(j)
    k2, _ = masukan_windows.kunci_dan_label(j.lower())
    assert k1 == k2 and k1.startswith("KB-") and label == "USB VID 1EAB PID 1D06"
    _, label = masukan_windows.kunci_dan_label(r"\\?\ROOT#RDP_KBD#0000#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}")
    assert label == "Keyboard RDP_KBD"


def test_serial_banyak_port():
    baris, sisa = masukan_serial.pecah_baris(b"", b"PSD1.A\r\nPSD1.")
    assert baris == ["PSD1.A"] and sisa == b"PSD1."
    baris, sisa = masukan_serial.pecah_baris(sisa, b"B.C\r")
    assert baris == ["PSD1.B.C"] and sisa == b""

    class Port:
        def __init__(self, potongan):
            self.p = list(potongan)

        def read(self, n):
            if self.p:
                return self.p.pop(0)
            time.sleep(0.01)
            return b""

        def close(self):
            pass

    Info = type("Info", (), {})
    a, b = Info(), Info()
    a.device, a.hwid, a.description, a.serial_number = "COM5", "USB VID:PID=0C2E:0B61 SER=1", "Honeywell", "1"
    b.device, b.hwid, b.description, b.serial_number = "COM7", "USB VID:PID=1EAB:1D06", "Netum", None
    a.vid, a.pid, b.vid, b.pid = 0x0C2E, 0x0B61, 0x1EAB, 0x1D06
    data = {"COM5": [b"04A1", b"B2C3\r\n"], "COM7": [b"PSD1.X.Y\r"]}
    dapat = []
    r = masukan_serial.PembacaSerial(lambda k, l, t: dapat.append((l.split(" ")[0], t)),
                                     daftar_port=lambda: [a, b], buka=lambda d: Port(data[d]))
    terhubung = r.pindai()
    time.sleep(0.3)
    r.berjalan = False
    assert sorted(dapat) == [("COM5", "04A1B2C3"), ("COM7", "PSD1.X.Y")]
    assert len({k for k, _ in terhubung}) == 2


# ------------------------------------------------------------------ ujung ke ujung
@pytest.fixture
def pos_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENSIKU_POS_DATA", str(tmp_path / "posdata"))
    return tmp_path


def _siapkan_server(app, client):
    for nama, urut in (("Gerbang Depan", 1), ("Gerbang Belakang", 2)):
        client.post("/sistem/perangkat-scan", data={"aksi": "gerbang_simpan", "nama": nama,
                                                    "mode": "auto", "urutan": urut})
    client.post("/sistem/perangkat-scan", data={"aksi": "pos_tambah", "nama": "PC Satpam"})
    with app.app_context():
        db = connect()
        p = db.execute("SELECT kode_pasang FROM pos").fetchone()
        g = {r["nama"]: r["id"] for r in db.execute("SELECT id, nama FROM gerbang").fetchall()}
        db.close()
    return p["kode_pasang"], g


def _scan(mesin, kunci, teks, t0):
    """Ketikan scanner mode keyboard dari alat `kunci` (cepat, diakhiri Enter)."""
    t = t0
    for ch in teks.upper():
        vk = 0xBE if ch == "." else ord(ch)
        if ch.isalpha():
            mesin.tombol(kunci, f"Scanner {kunci}", 0x10, True, t)
        mesin.tombol(kunci, f"Scanner {kunci}", vk, True, t)
        mesin.tombol(kunci, f"Scanner {kunci}", vk, False, t)
        if ch.isalpha():
            mesin.tombol(kunci, f"Scanner {kunci}", 0x10, False, t)
        t += 0.003
    mesin.tombol(kunci, f"Scanner {kunci}", 0x0D, True, t)
    return t


def _ts(jam, menit):
    return dt(2030, 1, 7, jam, menit, tzinfo=utils.zona()).timestamp()


def _presensi(app, siswa_id):
    with app.app_context():
        db = connect()
        r = db.execute("SELECT jam_masuk, gerbang_masuk, jam_pulang, gerbang_pulang FROM presensi "
                       "WHERE siswa_id = ?", (siswa_id,)).fetchone()
        db.close()
    return r


def test_pos_ujung_ke_ujung(pos_env, app, client, seed, clock):
    from presensiku_pos.mesin import Mesin
    kode_pasang, g = _siapkan_server(app, client)
    sesi = SesiFlask(app.test_client())
    jam = {"t": _ts(6, 45)}
    m = Mesin(sesi=sesi, waktu=lambda: jam["t"])
    assert not m.terpasang and "belum dipasangkan" in m.umpan()["peringatan"]
    with pytest.raises(Exception):
        m.pasang(SERVER, "SALAH-123")
    m.pasang(SERVER.replace("http://", "http://"), kode_pasang)
    assert m.terpasang and [x["nama"] for x in m.gerbang()] == ["Gerbang Depan", "Gerbang Belakang"]
    assert len(m.data.siswa) == 3 and m.data.secret

    # tiga scanner baru di-scan bersamaan (selang-seling) + keyboard biasa diketik pelan
    t = 1000.0
    for kunci, siswa in (("KB-1", "ahmad"), ("KB-2", "siti"), ("COM-9", None)):
        if kunci.startswith("KB"):
            _scan(m, kunci, seed[siswa]["qr"], t)
    m.teks_com("COM-9", "COM9 – Honeywell", seed["budi"]["qr"])
    for i, vk in enumerate((0x31, 0x32, 0x33, 0x34, 0x0D)):
        m.tombol("KB-KEYBOARD", "Keyboard laptop", vk, True, 2000 + i * 0.3)
    u = m.umpan()
    assert {b["kunci"] for b in u["baru"]} == {"KB-1", "KB-2", "COM-9"}   # keyboard biasa tidak ditanya
    assert u["pilihan_gerbang"][0]["nama"] == "Gerbang Depan"

    # petugas memilih gerbang di layar; scan yang tertahan langsung diproses
    m.petakan("KB-1", g["Gerbang Depan"])
    m.petakan("KB-2", g["Gerbang Depan"])
    m.petakan("COM-9", g["Gerbang Belakang"])
    assert m.petakan("KB-X", 99999)["ok"] is False
    while m.kirim_sekali() > 0:
        pass
    assert _presensi(app, seed["ahmad"]["id"])["gerbang_masuk"] == "Gerbang Depan"
    assert _presensi(app, seed["budi"]["id"])["gerbang_masuk"] == "Gerbang Belakang"
    u = m.umpan()
    nama = {i["siswa"]["nama"]: i for i in u["item"] if i.get("siswa")}
    assert nama["Ahmad Fauzi"]["level"] == "success" and nama["Ahmad Fauzi"]["jenis"] == "masuk"
    assert u["hadir"] == {"Gerbang Depan": 2, "Gerbang Belakang": 1} and u["online"]
    assert not u["baru"] and m.peta_lokal == {}                     # pemetaan sudah di server
    m.sinkron()
    assert {s["kunci"] for s in m.cfg["scanner"]} >= {"KB-1", "KB-2", "COM-9"}

    # scan ganda dalam 60 detik di gerbang lain: diabaikan tanpa ke server
    jam["t"] = _ts(6, 45) + 20
    m.teks_com("COM-9", "COM9 – Honeywell", seed["ahmad"]["qr"])
    assert m.umpan()["item"][-1]["jenis"] == "ganda" and m.antrean.jumlah_belum() == 0

    # INTERNET PUTUS saat jam pulang: tetap tampil & tersimpan
    sesi.putus = True
    jam["t"] = _ts(14, 30)
    _scan(m, "KB-2", seed["ahmad"]["qr"], 3000)
    assert m.kirim_sekali() == -1 and not m.online
    for d in m.tertunda.values():
        d["t0"] -= 5
    m._selesaikan_tertunda()
    it = m.umpan()["item"][-1]
    assert it["jenis"] == "tersimpan" and it["siswa"]["nama"] == "Ahmad Fauzi"
    assert m.umpan()["antrean"] == 1
    # tetap jalan walau Pos dinyalakan ulang (antrean di disk)
    m2 = Mesin(sesi=sesi, waktu=lambda: jam["t"])
    assert m2.antrean.jumlah_belum() == 1 and m2.peta("KB-2")["gerbang"] == "Gerbang Depan"
    # internet kembali: terkirim dengan jam asli 14:30
    sesi.putus = False
    clock.set(14, 45)
    assert m2.kirim_sekali() == 1
    r = _presensi(app, seed["ahmad"]["id"])
    assert r["jam_pulang"] == "14:30:00" and r["gerbang_pulang"] == "Gerbang Depan"
    assert m2.antrean.jumlah_belum() == 0

    # kartu palsu: ditolak lokal, tidak masuk antrean
    m2.teks_com("COM-9", "COM9", "PSD1.PALSU.ABCDEFGH")
    assert m2.umpan()["item"][-1]["level"] == "error" and m2.antrean.jumlah_belum() == 0
    # abaikan alat (mis. keyboard yang mengetik cepat)
    m2.teks_com("COM-77", "COM77 – GPS", "$GPGGA,123")
    m2.petakan("COM-77", abaikan=True)
    m2.teks_com("COM-77", "COM77 – GPS", "$GPGGA,456")
    assert not m2.umpan()["baru"]


def _port_bebas():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_web_lokal(pos_env, app, client, seed):
    from presensiku_pos import web
    from presensiku_pos.mesin import Mesin
    kode_pasang, g = _siapkan_server(app, client)
    m = Mesin(sesi=SesiFlask(app.test_client()))
    port = _port_bebas()
    srv = web.mulai(m, port)
    dasar = f"http://127.0.0.1:{port}"

    def minta(path, data=None, header=None):
        req = urllib.request.Request(dasar + path, data=data, headers=header or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    try:
        st, isi = minta("/")
        assert st == 200 and "Pasang Presensiku Pos" in isi
        st, isi = minta("/pasang", f"server={SERVER}&kode=SALAH".encode())
        assert st == 400 and "kedaluwarsa" in isi
        st, isi = minta("/pasang", f"server={SERVER}&kode={kode_pasang}".encode())
        assert st == 200 and "layar_gerbang.js" in isi and "Scanner baru terdeteksi" in isi
        st, isi = minta("/statis/layar_gerbang.js")
        assert st == 200 and "LAYAR" in isi
        st, isi = minta("/api/umpan")
        assert st == 200 and json.loads(isi)["gerbang"] == ["Gerbang Depan", "Gerbang Belakang"]
        # situs lain di browser tidak boleh memerintah Pos; host asing (DNS rebinding) ditolak
        st, _ = minta("/api/petakan", b'{"kunci":"KB-1","abaikan":true}',
                      {"Origin": "https://jahat.example", "Content-Type": "application/json"})
        assert st == 403
        st, _ = minta("/api/umpan", header={"Host": "jahat.example:%d" % port})
        assert st == 403
        m.teks_com("COM-1", "COM1", seed["siti"]["qr"])
        st, isi = minta("/api/petakan", json.dumps({"kunci": "COM-1", "gerbang_id": g["Gerbang Depan"]}).encode(),
                        {"Origin": dasar, "Content-Type": "application/json"})
        assert st == 200 and json.loads(isi)["ok"]
    finally:
        srv.shutdown()
