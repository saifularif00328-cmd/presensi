from app.db import connect
from app.license import make_key, validate_key
from app.qr import make_payload, parse_payload

from .conftest import BASE_DAY, set_tier


def scan(client, code, mode="auto"):
    r = client.post("/presensi/api/scan", json={"code": code, "mode": mode, "metode": "tes"})
    assert r.status_code == 200
    return r.get_json()


def presensi_row(app, sid):
    with app.app_context():
        db = connect()
        row = db.execute("SELECT * FROM presensi WHERE siswa_id = ?", (sid,)).fetchone()
        db.close()
        return row


def test_qr_payload_roundtrip_and_tamper(app):
    with app.app_context():
        p = make_payload("ABCDEF0123456789")
        assert parse_payload(p) == "ABCDEF0123456789"
        assert parse_payload(p.lower()) == "ABCDEF0123456789"  # scanner kadang huruf kecil
        forged = p[:-1] + ("A" if p[-1] != "A" else "B")
        assert parse_payload(forged) is None
        assert parse_payload("PSD1.XXXX") is None
        assert parse_payload("hello") is None


def test_scan_masuk_ulang_pulang(app, client, seed, clock):
    ahmad = seed["ahmad"]
    clock.set(6, 50)
    r = scan(client, ahmad["qr"])
    assert r["ok"] and r["jenis"] == "masuk" and r["status"] == "Hadir"

    # scan ulang sebelum jam pulang → peringatan dengan waktu absen sebelumnya
    clock.set(7, 5)
    r = scan(client, ahmad["qr"])
    assert not r["ok"] and r["level"] == "warning" and "06:50" in r["pesan"]

    # mode masuk eksplisit juga ditolak
    r = scan(client, ahmad["qr"], "masuk")
    assert not r["ok"] and "06:50" in r["pesan"]

    # scan setelah batas mulai pulang (11:00) sebelum jam pulang (14:00) → Pulang Cepat
    clock.set(11, 30)
    r = scan(client, ahmad["qr"])
    assert r["ok"] and r["jenis"] == "pulang" and r["status"] == "Pulang Cepat"

    clock.set(14, 30)
    r = scan(client, ahmad["qr"])
    assert not r["ok"] and "pulang pukul 11:30" in r["pesan"]

    row = presensi_row(app, ahmad["id"])
    assert row["keterangan"] == "H" and row["jam_masuk"] == "06:50:00"
    assert row["status_pulang"] == "Pulang Cepat"


def test_scan_telat_dan_pulang_tepat(app, client, seed, clock):
    siti = seed["siti"]
    clock.set(7, 30)
    assert scan(client, siti["qr"])["status"] == "Telat"
    clock.set(14, 5)
    assert scan(client, siti["qr"])["status"] == "Tepat Waktu"


def test_pulang_tanpa_masuk_ditolak(client, seed, clock):
    clock.set(14, 0)
    r = scan(client, seed["budi"]["qr"], "pulang")
    assert not r["ok"] and "Belum absen masuk" in r["pesan"]


def test_qr_palsu_dan_kartu_lama(app, client, seed, clock):
    r = scan(client, "PSD1.0000000000000000.AAAAAAAA")
    assert not r["ok"] and r["level"] == "error"
    old = seed["ahmad"]["qr"]
    client.post(f"/master/siswa/{seed['ahmad']['id']}/ganti-qr")
    r = scan(client, old)
    assert not r["ok"] and "tidak berlaku" in r["pesan"]


def test_hari_libur_dilewati(client, seed, clock):
    client.post("/sistem/libur", data={"tanggal": BASE_DAY.date().isoformat(),
                                       "keterangan": "Libur uji"})
    r = scan(client, seed["ahmad"]["qr"])
    assert not r["ok"] and "Libur uji" in r["pesan"]


def test_aturan_jam_per_kelas(app, client, seed, clock):
    client.post("/kedisiplinan/aturan-jam", data={
        "nama": "Kelas 8", "jenjang": "8", "jam_masuk": "07:30", "batas_telat": "07:45",
        "batas_pulang_cepat": "12:00", "jam_pulang": "15:00", "jam_tutup": "16:00"})
    clock.set(7, 40)
    assert scan(client, seed["budi"]["qr"])["status"] == "Hadir"   # jenjang 8: telat > 07:45
    assert scan(client, seed["ahmad"]["qr"])["status"] == "Telat"  # default: telat > 07:15


def test_tutup_harian_alpha_dan_belum_pulang(app, client, seed, clock):
    clock.set(7, 0)
    scan(client, seed["ahmad"]["qr"])
    clock.set(16, 30)
    from app.services.attendance import close_day
    with app.app_context():
        db = connect()
        n = close_day(db)
        assert close_day(db) == 0  # idempoten
        q = db.execute("SELECT COUNT(*) FROM notif_queue WHERE jenis = 'alpha'").fetchone()[0]
        db.close()
    assert n == 2
    assert presensi_row(app, seed["ahmad"]["id"])["status_pulang"] == "Belum Pulang"
    assert presensi_row(app, seed["siti"]["id"])["keterangan"] == "A"
    assert q == 1  # hanya Budi yang punya nomor WA


def test_izin_disetujui_jadi_sakit_dan_notif(app, client, seed, clock):
    sid = seed["budi"]["id"]
    d = BASE_DAY.date().isoformat()
    client.post("/perizinan/izin", data={"siswa_id": sid, "jenis": "Sakit",
                                         "tanggal_mulai": d, "tanggal_selesai": d,
                                         "alasan": "demam"})
    r = client.post("/perizinan/izin/1/setujui", data={})
    assert r.status_code == 302
    assert presensi_row(app, sid)["keterangan"] == "S"
    with app.app_context():
        db = connect()
        n = db.execute("SELECT nomor, pesan FROM notif_queue WHERE jenis = 'izin'").fetchall()
        db.close()
    assert len(n) == 1 and n[0]["nomor"] == "6281299998888" and "Budi" in n[0]["pesan"]
    # siswa ternyata datang → berubah jadi Hadir
    clock.set(7, 0)
    scan(client, seed["budi"]["qr"])
    assert presensi_row(app, sid)["keterangan"] == "H"


def test_presensi_manual(app, client, seed, clock):
    sid = seed["siti"]["id"]
    client.post("/presensi/manual", data={"kelas_id": 1, "tanggal": BASE_DAY.date().isoformat(),
                                          f"ket_{sid}": "D", f"cat_{sid}": "Lomba"})
    row = presensi_row(app, sid)
    assert row["keterangan"] == "D" and row["sumber"] == "manual" and row["catatan"] == "Lomba"


def test_antrian_wa_offline_lalu_online(app, client, seed, clock, monkeypatch):
    from app.services import notify
    from app import utils
    clock.set(6, 55)
    scan(client, seed["ahmad"]["qr"])
    with app.app_context():
        db = connect()
        from app.db import set_setting
        set_setting("fonnte_token", utils.encrypt("tok123"), db=db)
        monkeypatch.setattr(notify, "is_online", lambda timeout=4: False)
        assert notify.process_queue(db) == 0
        st = db.execute("SELECT status FROM notif_queue").fetchone()["status"]
        assert st == "Menunggu Koneksi"

        sent = []
        monkeypatch.setattr(notify, "is_online", lambda timeout=4: True)
        monkeypatch.setattr(notify, "send_one",
                            lambda tok, nomor, pesan: (sent.append((tok, nomor)) or True, None))
        assert notify.process_queue(db) == 1
        assert sent == [("tok123", "6281234567890")]
        assert db.execute("SELECT status FROM notif_queue").fetchone()["status"] == "Terkirim"
        db.close()


def test_wa_toggle_nonaktif(app, client, seed, clock):
    client.post("/notifikasi/pengaturan", data={"wa_on_pulang": "1"})  # masuk dimatikan
    scan(client, seed["ahmad"]["qr"])
    with app.app_context():
        db = connect()
        assert db.execute("SELECT COUNT(*) FROM notif_queue").fetchone()[0] == 0
        db.close()


def test_lisensi_dan_tier(app, client):
    k = make_key("AAAA-BBBB-CCCC-DDDD", "pro")
    assert validate_key(k, "AAAA-BBBB-CCCC-DDDD") == "pro"
    assert validate_key(k, "AAAA-BBBB-CCCC-EEEE") is None
    set_tier(app, None)
    assert client.get("/perizinan/izin").status_code == 402
    assert client.get("/ibadah/tap").status_code == 402
    assert client.get("/presensi/scan").status_code == 200
    set_tier(app, "pro")
    assert client.get("/perizinan/izin").status_code == 200
    assert client.get("/ibadah/tap").status_code == 402


def test_role_piket(app, client):
    client.post("/sistem/users", data={"username": "piket", "nama": "Pak Piket", "role": "piket",
                                       "password": "rahasia1", "aktif": "1"})
    c = app.test_client()
    assert c.post("/login", data={"username": "piket", "password": "rahasia1"}).status_code == 302
    assert c.get("/presensi/scan").status_code == 200
    assert c.get("/master/siswa").status_code == 403
    assert c.get("/kedisiplinan/pelanggaran").status_code == 403


def test_import_csv(app, client):
    import io
    csv = "nis;nama;kelas;wa_ibu\n2001;Dewi Lestari;9B;081200000001\n2002;Eko Prasetyo;9B;\n"
    r = client.post("/master/siswa/import", data={"file": (io.BytesIO(csv.encode()), "s.csv")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    with app.app_context():
        db = connect()
        rows = db.execute("SELECT s.nama, k.nama AS kelas, s.qr_token FROM siswa s "
                          "JOIN kelas k ON k.id = s.kelas_id").fetchall()
        db.close()
    assert {r["nama"] for r in rows} == {"Dewi Lestari", "Eko Prasetyo"}
    assert all(r["kelas"] == "9B" and r["qr_token"] for r in rows)


def test_exports(client, seed, clock):
    scan(client, seed["ahmad"]["qr"])
    for url in ["/presensi/rekap?format=xlsx", "/presensi/rekap?format=pdf",
                "/presensi/smt?format=xlsx", "/presensi/smt?format=pdf",
                "/rekap-kelas/export?format=pdf", "/rekap-kelas/export?kelas_id=1&format=xlsx",
                "/master/kartu/pdf?kelas_id=1", "/master/siswa/import/template.xlsx",
                "/kedisiplinan/pelanggaran?format=xlsx", "/ibadah/rekap?format=pdf",
                "/sistem/backup", f"/master/siswa/{seed['ahmad']['id']}/qr.png"]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert len(r.data) > 100, url


def test_csrf_wajib(tmp_path, clock):
    from app import create_app
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "c.db")}, start_jobs=False)
    c = app.test_client()
    assert c.post("/login", data={"username": "admin", "password": "admin123"}).status_code == 400
    c.get("/login")
    with c.session_transaction() as sess:
        token = sess["_csrf"]
    r = c.post("/login", data={"username": "admin", "password": "admin123", "_csrf": token})
    assert r.status_code == 302


def test_api_cabang_token(app, client):
    assert client.get("/sistem/api/ringkasan").status_code == 401
    with app.app_context():
        from app.db import get_setting
        tok = get_setting("cabang_api_token")
    r = client.get("/sistem/api/ringkasan", headers={"X-Cabang-Token": tok})
    assert r.status_code == 200 and "total" in r.get_json()


def test_semua_halaman_render(app, client, seed, clock):
    scan(client, seed["ahmad"]["qr"])
    skip = {"/static/<path:filename>", "/uploads/<path:filename>", "/logout", "/favicon.ico"}
    urls = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.rule in skip or "/api/" in rule.rule:
            continue
        url = rule.rule.replace("<int:sid>", str(seed["ahmad"]["id"]))
        if "<" in url:
            continue
        urls.append(url)
    for extra in ["/master/kelas?edit=1", "/presensi/manual?kelas_id=1",
                  "/perizinan/izin?status=semua", "/kedisiplinan/pelanggaran?tab=siswa",
                  "/kedisiplinan/pelanggaran?tab=jenis", "/presensi/monitor?kelas_id=1"]:
        urls.append(extra)
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, f"{url} → {r.status_code}"
    assert client.get("/presensi/api/monitor").get_json()["stats"]["masuk"] == 1


def test_kartu_semua_template(app, client, seed):
    from app.services.kartu import ORIENTASI, TEMPLATES, WARNA
    for t in TEMPLATES:
        for o in ORIENTASI:
            r = client.get(f"/master/kartu/pdf?kelas_id=1&template={t}&orientasi={o}&warna=emas")
            assert r.status_code == 200 and r.data[:4] == b"%PDF", (t, o)
    r = client.get("/master/kartu/pdf?pratinjau=1&template=elegan&orientasi=v&warna=hijau")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    r = client.get("/master/kartu/pdf?pratinjau=1&template=modern&orientasi=h&format=png")
    assert r.status_code == 200 and r.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert set(WARNA)  # pilihan warna tersedia
    # pilihan terakhir (bukan pratinjau) tersimpan sebagai default
    with app.app_context():
        from app.db import get_setting
        assert get_setting("kartu_template") == "gradien"
        assert get_setting("kartu_orientasi") == "v"
