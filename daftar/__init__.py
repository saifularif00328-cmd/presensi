"""Halaman depan presensiku.biz.id: masuk ke sekolah + pendaftaran demo gratis.

Aplikasi kecil terpisah (user sistem "presensi", 127.0.0.1:7000). Formulir pendaftaran hanya
menulis permintaan ke folder antrean; pembuatan sekolah (database, layanan, Nginx) dikerjakan
oleh `presensi-sekolah proses-antrean` sebagai root — aplikasi web ini tidak punya hak root.

    /srv/presensi/_antrean/masuk/<token>.json   permintaan baru (diproses lalu dipindah)
    /srv/presensi/_antrean/hasil/<token>.json   hasil: siap / gagal
    /srv/presensi/_publik.json                  daftar kode terpakai + jumlah demo aktif
    /srv/presensi/_konfigurasi.json             nomor WA vendor, lama demo, kuota demo
"""
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

KODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,40}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
# kode yang tidak boleh dipakai sekolah (bertabrakan dengan halaman depan / istilah umum)
CADANGAN = {"daftar", "cek-kode", "aset", "static", "api", "admin", "www", "demo", "login",
            "logout", "portal", "masuk", "beranda", "presensi", "presensiku", "app", "mail",
            "status", "bantuan", "harga", "kontak", "favicon-ico", "robots-txt", "sekolah",
            "vendor"}
JENJANG = ["SD / MI", "SMP / MTs", "SMA / MA", "SMK", "Pesantren", "Lainnya"]
ZONA = {"Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT"}
KONFIGURASI_AWAL = {"wa": "", "nama": "Presensiku", "hari_demo": 7, "maks_demo": 5,
                    "henti_setelah": 14}
MAKS_PER_IP = 3          # pendaftaran per alamat IP per 24 jam


def akar():
    return os.environ.get("PRESENSI_SRV", "/srv/presensi")


def domain():
    return os.environ.get("PRESENSI_DOMAIN", "presensiku.biz.id")


def _baca_json(path, bawaan):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return bawaan


def konfigurasi():
    return {**KONFIGURASI_AWAL, **_baca_json(os.path.join(akar(), "_konfigurasi.json"), {})}


def publik():
    return {"kode": [], "demo_aktif": 0,
            **_baca_json(os.path.join(akar(), "_publik.json"), {})}


def dir_masuk():
    return os.path.join(akar(), "_antrean", "masuk")


def dir_hasil():
    return os.path.join(akar(), "_antrean", "hasil")


def normal_wa(teks):
    """0812-3456-7890 / +62 812... / 812... -> 628123456789 (None bila tidak valid)."""
    d = re.sub(r"\D", "", teks or "")
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    return d if re.fullmatch(r"628\d{7,12}", d) else None


def tautan_wa(nomor, pesan):
    return f"https://wa.me/{nomor}?text={quote(pesan)}" if nomor else ""


def semua_permintaan():
    """Permintaan yang masih antre (status menunggu) dan yang sudah diproses."""
    out = []
    for folder, status in ((dir_masuk(), "menunggu"), (dir_hasil(), None)):
        try:
            nama_file = os.listdir(folder)
        except OSError:
            continue
        for nama in nama_file:
            if nama.endswith(".json") and not nama.startswith("."):
                d = _baca_json(os.path.join(folder, nama), None)
                if isinstance(d, dict):
                    if status:
                        d["status"] = status
                    out.append(d)
    return out


def cek_kode(kode, antre=None):
    """(boleh, pesan) untuk kode alamat sekolah."""
    if not KODE_RE.match(kode or ""):
        return False, "Kode 2–31 karakter: huruf kecil, angka, atau tanda minus (mis. smpn1malang)."
    if kode in CADANGAN:
        return False, "Kode ini tidak bisa dipakai. Pilih kode lain."
    antre = semua_permintaan() if antre is None else antre
    if kode in publik()["kode"] or any(
            p.get("kode") == kode and p.get("status") in ("menunggu", "siap") for p in antre):
        return False, "Kode sudah dipakai sekolah lain."
    return True, "Kode tersedia."


def _ip():
    # alamat asli dari Cloudflare hanya dipercaya bila permintaan datang dari Nginx lokal
    if request.remote_addr == "127.0.0.1":
        return request.headers.get("CF-Connecting-IP") or request.remote_addr
    return request.remote_addr or ""


def _turnstile_ok(token):
    secret = os.environ.get("DAFTAR_TURNSTILE_SECRET")
    if not secret:
        return True
    try:
        import requests
        r = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify",
                          data={"secret": secret, "response": token or "", "remoteip": _ip()},
                          timeout=10)
        return bool(r.json().get("success"))
    except Exception:  # noqa: BLE001 — server verifikasi tak terjangkau: tolak
        return False


def _kunci_rahasia():
    path = os.path.join(akar(), "_daftar", "secret")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        kunci = secrets.token_hex(32)
        with open(path, "w", encoding="utf-8") as f:
            f.write(kunci)
        os.chmod(path, 0o600)
        return kunci


def periksa_formulir(f, antre, ip, sekarang):
    """Kembalikan (data_bersih, galat{kolom: pesan})."""
    g = {}
    d = {k: (f.get(k) or "").strip() for k in (
        "nama_sekolah", "jenjang", "kota", "zona", "nama", "jabatan", "wa", "email",
        "jumlah_siswa", "kode")}
    d["kode"] = d["kode"].lower()
    if not 3 <= len(d["nama_sekolah"]) <= 120:
        g["nama_sekolah"] = "Isi nama sekolah (3–120 karakter)."
    if d["jenjang"] not in JENJANG:
        g["jenjang"] = "Pilih jenjang."
    if not 2 <= len(d["kota"]) <= 80:
        g["kota"] = "Isi kabupaten / kota."
    if d["zona"] not in ZONA:
        g["zona"] = "Pilih zona waktu."
    if not 2 <= len(d["nama"]) <= 80:
        g["nama"] = "Isi nama Anda."
    d["jabatan"] = d["jabatan"][:60]
    wa = normal_wa(d["wa"])
    if not wa:
        g["wa"] = "Nomor WhatsApp tidak valid (mis. 0812xxxxxxx)."
    d["wa"] = wa or d["wa"]
    if d["email"] and (len(d["email"]) > 120 or not EMAIL_RE.match(d["email"])):
        g["email"] = "Email tidak valid (boleh dikosongkan)."
    try:
        d["jumlah_siswa"] = int(d["jumlah_siswa"])
        if not 1 <= d["jumlah_siswa"] <= 20000:
            raise ValueError
    except ValueError:
        g["jumlah_siswa"] = "Isi perkiraan jumlah siswa."
    boleh, pesan = cek_kode(d["kode"], antre)
    if not boleh:
        g["kode"] = pesan
    pw = f.get("password") or ""
    if len(pw) < 8:
        g["password"] = "Password minimal 8 karakter."
    elif pw != (f.get("password2") or ""):
        g["password2"] = "Ulangi password dengan sama persis."
    if not f.get("setuju"):
        g["setuju"] = "Centang persetujuan terlebih dahulu."
    if not g:
        batas = (sekarang - timedelta(hours=24)).isoformat(timespec="seconds")
        if sum(1 for p in antre if p.get("ip") == ip and (p.get("dibuat") or "") >= batas) \
                >= MAKS_PER_IP:
            g["umum"] = "Terlalu banyak pendaftaran dari jaringan ini. Coba lagi besok."
        elif wa and any(p.get("wa") == wa and p.get("status") in ("menunggu", "siap")
                        for p in antre):
            g["wa"] = "Nomor ini sudah pernah mendaftar demo. Hubungi kami untuk bantuan."
    d["password_hash"] = generate_password_hash(pw) if not g else ""
    return d, g


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=None, WAKTU_ISI_MIN=3)
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _kunci_rahasia()
    tanda = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="formulir-demo")

    def tampil_beranda(nilai=None, galat=None, status=200):
        k = konfigurasi()
        p = publik()
        antre = sum(1 for x in semua_permintaan() if x.get("status") == "menunggu")
        berakhir = request.args.get("berakhir", "")
        if not KODE_RE.match(berakhir):
            berakhir = ""
        return render_template(
            "beranda.html", k=k, domain=domain(), nilai=nilai or {}, galat=galat or {},
            JENJANG=JENJANG, ZONA=ZONA, token_waktu=tanda.dumps(int(time.time())),
            penuh=p["demo_aktif"] + antre >= int(k["maks_demo"]),
            turnstile=os.environ.get("DAFTAR_TURNSTILE_SITE", ""), berakhir=berakhir,
            wa_tanya=tautan_wa(k["wa"], f"Halo {k['nama']}, saya ingin bertanya tentang "
                                        "aplikasi Presensi Siswa Digital."),
            wa_berakhir=tautan_wa(k["wa"], f"Halo {k['nama']}, masa demo sekolah kami "
                                           f"(kode: {berakhir}) sudah berakhir. Kami ingin "
                                           "memperpanjang lisensi. Mohon info paket dan "
                                           "cara pembayarannya. Terima kasih.")), status

    @app.get("/")
    def beranda():
        return tampil_beranda()

    @app.get("/cek-kode")
    def kode_tersedia():
        boleh, pesan = cek_kode((request.args.get("kode") or "").strip().lower())
        return jsonify(ok=boleh, pesan=pesan)

    @app.post("/daftar")
    def daftar():
        f = request.form
        if f.get("situs"):                       # kolom jebakan bot (disembunyikan)
            abort(400)
        try:
            dibuka = tanda.loads(f.get("t", ""), max_age=3 * 3600)
        except BadData:
            return tampil_beranda(f, {"umum": "Formulir kedaluwarsa. Silakan isi ulang."}, 400)
        if time.time() - dibuka < app.config["WAKTU_ISI_MIN"]:
            abort(400)
        if not _turnstile_ok(f.get("cf-turnstile-response")):
            return tampil_beranda(f, {"umum": "Verifikasi keamanan gagal. Coba lagi."}, 400)
        k = konfigurasi()
        antre = semua_permintaan()
        if publik()["demo_aktif"] + sum(1 for x in antre if x.get("status") == "menunggu") \
                >= int(k["maks_demo"]):
            return tampil_beranda(f, {"umum": "Kuota demo sedang penuh. Hubungi kami lewat "
                                              "WhatsApp untuk dijadwalkan."}, 400)
        sekarang = datetime.now()
        ip = _ip()
        d, galat = periksa_formulir(f, antre, ip, sekarang)
        if galat:
            return tampil_beranda(f, galat, 400)
        token = secrets.token_urlsafe(18)
        data = {"token": token, "dibuat": sekarang.isoformat(timespec="seconds"), "ip": ip,
                **d}
        os.makedirs(dir_masuk(), exist_ok=True)
        sementara = os.path.join(dir_masuk(), f".tmp-{token}")
        with open(sementara, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.chmod(sementara, 0o640)
        os.replace(sementara, os.path.join(dir_masuk(), f"{token}.json"))
        return redirect(url_for("status_halaman", token=token))

    def _cari(token):
        if not TOKEN_RE.match(token):
            abort(404)
        hasil = _baca_json(os.path.join(dir_hasil(), f"{token}.json"), None)
        if hasil:
            return hasil
        masuk = _baca_json(os.path.join(dir_masuk(), f"{token}.json"), None)
        if masuk:
            return {"status": "menunggu", "kode": masuk.get("kode"),
                    "nama_sekolah": masuk.get("nama_sekolah")}
        abort(404)

    def _publik_status(h):
        return {"status": h.get("status"), "pesan": h.get("pesan", ""),
                "kode": h.get("kode"), "nama_sekolah": h.get("nama_sekolah"),
                "url": h.get("url", ""), "username": h.get("username", ""),
                "sampai": h.get("sampai", "")}

    @app.get("/daftar/<token>")
    def status_halaman(token):
        k = konfigurasi()
        h = _publik_status(_cari(token))
        return render_template(
            "status.html", h=h, k=k, domain=domain(),
            wa_bantuan=tautan_wa(k["wa"], f"Halo {k['nama']}, saya baru mendaftar demo untuk "
                                          f"{h['nama_sekolah']} (kode: {h['kode']}). "
                                          "Mohon dibantu."))

    @app.get("/daftar/<token>/status")
    def status_json(token):
        return jsonify(_publik_status(_cari(token)))

    from .vendor import pasang
    pasang(app)

    @app.after_request
    def keamanan(resp):
        if request.path.startswith("/vendor"):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    return app
