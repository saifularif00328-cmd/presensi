"""Panel pribadi vendor: https://presensiku.biz.id/vendor

Masuk dengan password + kode 6 digit Google Authenticator (akun dibuat dengan
`presensi-sekolah akun-vendor`). Panel ini berjalan tanpa hak root: perubahan (perpanjang,
nonaktif, tambah sekolah, pengaturan) dikirim sebagai perintah ke antrean dan dijalankan oleh
`presensi-sekolah proses-antrean` (root); data tampilan dibaca dari _ringkasan.json.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint("vendor", __name__, url_prefix="/vendor")

MAKS_GAGAL = 5                      # per IP, lalu dikunci 15 menit
MAKS_GAGAL_GLOBAL = 20              # semua IP dalam 1 jam
_gagal = {}                         # ip -> [waktu gagal]
_kode_terpakai = {}                 # username -> langkah TOTP terakhir (cegah pakai ulang)


# ------------------------------------------------------------------ TOTP (RFC 6238)

def totp(rahasia, t=None, langkah=30, digit=6):
    kunci = base64.b32decode(rahasia.upper() + "=" * (-len(rahasia) % 8))
    pencacah = int((time.time() if t is None else t) // langkah)
    h = hmac.new(kunci, struct.pack(">Q", pencacah), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digit:0{digit}d}"


def cek_totp(rahasia, kode, username):
    kode = (kode or "").replace(" ", "")
    if len(kode) != 6 or not kode.isdigit():
        return False
    sekarang = int(time.time() // 30)
    for geser in (-1, 0, 1):                       # toleransi jam HP ±30 detik
        langkah = sekarang + geser
        if hmac.compare_digest(totp(rahasia, langkah * 30), kode):
            if _kode_terpakai.get(username, -1) >= langkah:
                return False
            _kode_terpakai[username] = langkah
            return True
    return False


# ------------------------------------------------------------------ data & perintah

def _akar():
    from . import akar
    return akar()


def _akun():
    from . import _baca_json
    return _baca_json(os.path.join(_akar(), "_daftar", "vendor_akun.json"), None)


def ringkasan():
    from . import _baca_json
    data = _baca_json(os.path.join(_akar(), "_ringkasan.json"), {})
    return data.get("dibuat", ""), data.get("sekolah", {})


def kirim_perintah(aksi, **data):
    """Tulis perintah ke antrean root lalu tunggu hasilnya (biasanya < 2 detik)."""
    from . import _baca_json
    folder = os.path.join(_akar(), "_antrean", "perintah")
    os.makedirs(folder, exist_ok=True)
    pid = secrets.token_urlsafe(18)
    sementara = os.path.join(folder, f".tmp-{pid}")
    with open(sementara, "w", encoding="utf-8") as f:
        json.dump({"aksi": aksi, "data": data, "waktu": datetime.now().isoformat(timespec="seconds"),
                   "ip": _ip()}, f, ensure_ascii=False)
    os.chmod(sementara, 0o640)
    os.replace(sementara, os.path.join(folder, f"{pid}.json"))
    pekerja = current_app.config.get("JALANKAN_PEKERJA")    # pengujian: jalankan langsung
    if pekerja:
        pekerja()
    hasil = os.path.join(_akar(), "_antrean", "hasil", f"{pid}.json")
    batas = time.time() + current_app.config.get("TUNGGU_PERINTAH", 30)
    while time.time() < batas:
        r = _baca_json(hasil, None)
        if r:
            return r
        time.sleep(0.3)
    return {"status": "menunggu", "pesan": "Perintah masih diproses. Muat ulang halaman sebentar lagi."}


def _ip():
    if request.remote_addr == "127.0.0.1":
        return request.headers.get("CF-Connecting-IP") or request.remote_addr
    return request.remote_addr or ""


def _flash_hasil(r):
    flash(r.get("pesan") or r.get("status"), "ok" if r.get("status") == "siap" else
          ("info" if r.get("status") == "menunggu" else "er"))


def sisa_hari(s):
    try:
        return (datetime.strptime(s.get("sampai") or "", "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def keadaan(s):
    """Label status untuk tampilan: demo / aktif / akan_habis / habis / nonaktif / berhenti."""
    st, sisa = s.get("status"), sisa_hari(s)
    if st in ("nonaktif", "berhenti"):
        return st
    if sisa is not None and sisa < 0:
        return "habis"
    if st == "uji_coba":
        return "demo"
    if sisa is not None and sisa <= 14:
        return "akan_habis"
    return "aktif"


def wa_sekolah(s, pesan):
    from . import tautan_wa
    return tautan_wa((s.get("pendaftar") or {}).get("wa"), pesan)


def _ram_disk():
    info = {}
    try:
        with open("/proc/meminfo") as f:
            m = {b[0].rstrip(":"): int(b[1]) for b in (baris.split() for baris in f) if len(b) >= 2}
        info["ram"] = round(100 - m["MemAvailable"] * 100 / m["MemTotal"])
        info["ram_total"] = round(m["MemTotal"] / 1024 / 1024, 1)
    except (OSError, KeyError, ValueError):
        pass
    try:
        st = os.statvfs(_akar())
        info["disk"] = round(100 - st.f_bavail * 100 / st.f_blocks)
        info["disk_total"] = round(st.f_blocks * st.f_frsize / 1024 ** 3)
    except (OSError, ZeroDivisionError):
        pass
    return info


# ------------------------------------------------------------------ login

def wajib_masuk(view):
    @wraps(view)
    def w(*a, **kw):
        akun = _akun()
        if not akun or session.get("vendor") != akun["username"] \
                or session.get("vendor_versi") != akun.get("versi"):
            return redirect(url_for("vendor.masuk"))
        if request.method == "POST":
            dikirim = request.form.get("_csrf") or ""
            if not hmac.compare_digest(dikirim, session.get("csrf", "")):
                abort(400)
        return view(*a, **kw)
    return w


def _terkunci(ip):
    batas = time.time() - 15 * 60
    _gagal[ip] = [t for t in _gagal.get(ip, []) if t > batas]
    jam = time.time() - 3600
    total = sum(1 for daftar in _gagal.values() for t in daftar if t > jam)
    return len(_gagal[ip]) >= MAKS_GAGAL or total >= MAKS_GAGAL_GLOBAL


@bp.route("/masuk", methods=["GET", "POST"])
def masuk():
    akun = _akun()
    if not akun:
        return render_template("vendor/belum_ada_akun.html"), 503
    if request.method == "POST":
        ip = _ip()
        if _terkunci(ip):
            flash("Terlalu banyak percobaan gagal. Coba lagi 15 menit lagi.", "er")
            return render_template("vendor/masuk.html"), 429
        ok = (hmac.compare_digest(request.form.get("username", ""), akun["username"])
              and check_password_hash(akun["password_hash"], request.form.get("password", ""))
              and cek_totp(akun["totp"], request.form.get("kode"), akun["username"]))
        if ok:
            _gagal.pop(ip, None)
            session.clear()
            session.permanent = True
            session.update(vendor=akun["username"], vendor_versi=akun.get("versi"),
                           csrf=secrets.token_urlsafe(24))
            return redirect(url_for("vendor.dasbor"))
        _gagal.setdefault(ip, []).append(time.time())
        current_app.logger.warning("Login panel vendor gagal dari %s", ip)
        flash("Username, password, atau kode authenticator salah.", "er")
        return render_template("vendor/masuk.html"), 401
    return render_template("vendor/masuk.html")


@bp.post("/keluar")
@wajib_masuk
def keluar():
    session.clear()
    return redirect(url_for("vendor.masuk"))


# ------------------------------------------------------------------ halaman

@bp.get("/")
@wajib_masuk
def dasbor():
    dibuat, data = ringkasan()
    filt = request.args.get("f", "semua")
    cari = (request.args.get("q") or "").strip().lower()
    baris = []
    hitung = {"semua": 0, "demo": 0, "aktif": 0, "akan_habis": 0, "habis": 0, "nonaktif": 0,
              "berhenti": 0}
    for kode, s in data.items():
        k = keadaan(s)
        hitung["semua"] += 1
        hitung[k] = hitung.get(k, 0) + 1
        teks = " ".join([kode, s.get("nama", ""), (s.get("pendaftar") or {}).get("nama", ""),
                         (s.get("pendaftar") or {}).get("kota", "")]).lower()
        if (filt == "semua" or filt == k or (filt == "habis" and k in ("nonaktif", "berhenti"))) \
                and (not cari or cari in teks):
            baris.append({"kode": kode, "s": s, "keadaan": k, "sisa": sisa_hari(s)})
    urut = {"habis": 0, "akan_habis": 1, "demo": 2, "aktif": 3, "nonaktif": 4, "berhenti": 5}
    baris.sort(key=lambda b: (urut.get(b["keadaan"], 9), b["sisa"] if b["sisa"] is not None else 9999))
    from . import kesehatan, konfigurasi
    return render_template("vendor/dasbor.html", baris=baris, hitung=hitung, filt=filt, cari=cari,
                           dibuat=dibuat, sistem=_ram_disk(), k=konfigurasi(), sehat=kesehatan())


@bp.get("/sekolah/<kode>")
@wajib_masuk
def sekolah(kode):
    dibuat, data = ringkasan()
    s = data.get(kode) or abort(404)
    from . import domain, konfigurasi
    k = konfigurasi()
    pd = s.get("pendaftar") or {}
    sapa = f"Bapak/Ibu {pd['nama']}" if pd.get("nama") else "Bapak/Ibu"
    return render_template(
        "vendor/sekolah.html", kode=kode, s=s, pd=pd, keadaan=keadaan(s), sisa=sisa_hari(s),
        k=k, domain=domain(), hari_ini=date.today().isoformat(),
        wa_sapa=wa_sekolah(s, f"Halo {sapa}, saya dari {k['nama']} (aplikasi Presensi Siswa Digital "
                              f"{s.get('nama')}). "),
        wa_konfirmasi=wa_sekolah(s, f"Halo {sapa}, terima kasih. Lisensi aplikasi Presensi Siswa "
                                    f"Digital untuk {s.get('nama')} sudah aktif sampai "
                                    f"{s.get('sampai')}. Alamat aplikasi: https://{domain()}/{kode}"),
        wa_tagih=wa_sekolah(s, f"Halo {sapa}, masa {'demo' if s.get('status') == 'uji_coba' else 'langganan'} "
                               f"aplikasi Presensi Siswa Digital {s.get('nama')} berakhir "
                               f"{s.get('sampai')}. Apakah ingin dilanjutkan? Kami bantu info "
                               "paket dan cara pembayarannya."))


@bp.post("/sekolah/<kode>/perpanjang")
@wajib_masuk
def perpanjang(kode):
    f = request.form
    r = kirim_perintah("perpanjang", kode=kode, hari=f.get("hari") if f.get("hari") != "tanggal" else None,
                       sampai=f.get("sampai") if f.get("hari") == "tanggal" else None,
                       maks_siswa=f.get("maks_siswa") or None,
                       nominal=(f.get("nominal") or "0").replace(".", "").replace(",", ""),
                       catatan=f.get("catatan", ""))
    _flash_hasil(r)
    return redirect(url_for("vendor.sekolah", kode=kode))


@bp.post("/sekolah/<kode>/status")
@wajib_masuk
def ubah_status(kode):
    aksi = request.form.get("aksi")
    if aksi not in ("nonaktif", "aktifkan"):
        abort(400)
    _flash_hasil(kirim_perintah(aksi, kode=kode))
    return redirect(url_for("vendor.sekolah", kode=kode))


@bp.post("/sekolah/<kode>/kontak")
@wajib_masuk
def kontak(kode):
    f = request.form
    _flash_hasil(kirim_perintah("ubah_kontak", kode=kode, nama=f.get("nama", ""), wa=f.get("wa", ""),
                                jabatan=f.get("jabatan", ""), catatan=f.get("catatan", "")))
    return redirect(url_for("vendor.sekolah", kode=kode))


@bp.route("/tambah", methods=["GET", "POST"])
@wajib_masuk
def tambah():
    from . import JENJANG, ZONA, cek_kode, konfigurasi, normal_wa
    nilai, galat = request.form, {}
    if request.method == "POST":
        f = request.form
        boleh, pesan = cek_kode((f.get("kode") or "").strip().lower())
        if not boleh:
            galat["kode"] = pesan
        if not normal_wa(f.get("wa")):
            galat["wa"] = "Nomor WA kontak tidak valid."
        if len(f.get("password") or "") < 8:
            galat["password"] = "Password admin minimal 8 karakter."
        if not galat:
            r = kirim_perintah(
                "tambah", kode=f["kode"].strip().lower(), nama_sekolah=f.get("nama_sekolah", "").strip(),
                jenjang=f.get("jenjang"), kota=f.get("kota", "").strip(), zona=f.get("zona"),
                nama=f.get("nama", "").strip(), jabatan=f.get("jabatan", "").strip(),
                wa=normal_wa(f.get("wa")), email="", jumlah_siswa=f.get("maks_siswa") or 0,
                hari=f.get("hari"), maks_siswa=f.get("maks_siswa") or 0, demo=f.get("demo") == "1",
                password_hash=generate_password_hash(f["password"]), ip=_ip(),
                dibuat=datetime.now().isoformat(timespec="seconds"))
            _flash_hasil(r)
            if r.get("status") == "siap":
                return redirect(url_for("vendor.sekolah", kode=r["kode"]))
    return render_template("vendor/tambah.html", nilai=nilai, galat=galat, JENJANG=JENJANG,
                           ZONA=ZONA, k=konfigurasi())


@bp.route("/pengaturan", methods=["GET", "POST"])
@wajib_masuk
def pengaturan():
    from . import konfigurasi
    if request.method == "POST":
        f = request.form
        _flash_hasil(kirim_perintah("setel", wa=f.get("wa"), nama=f.get("nama"),
                                    hari_demo=f.get("hari_demo"), maks_demo=f.get("maks_demo"),
                                    henti_setelah=f.get("henti_setelah")))
        return redirect(url_for("vendor.pengaturan"))
    from . import kesehatan
    return render_template("vendor/pengaturan.html", k=konfigurasi(), sistem=_ram_disk(),
                           sehat=kesehatan())


def pasang(app):
    """Daftarkan panel vendor ke aplikasi halaman depan."""
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=8))
    app.config.update(SESSION_COOKIE_NAME="vendor_sesi", SESSION_COOKIE_PATH="/vendor",
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                      SESSION_COOKIE_SECURE=not app.config.get("TESTING"))
    app.register_blueprint(bp)

    @app.template_filter("rupiah")
    def rupiah(n):
        try:
            return "Rp" + f"{int(n):,}".replace(",", ".")
        except (TypeError, ValueError):
            return "-"

    @app.context_processor
    def _vendor_ctx():
        from . import konfigurasi
        return {"k": konfigurasi(), "csrf_vendor": session.get("csrf", "") if request.path.startswith("/vendor") else "",
                "LABEL_KEADAAN": {"demo": "Demo", "aktif": "Aktif", "akan_habis": "Akan habis",
                                  "habis": "Habis", "nonaktif": "Nonaktif", "berhenti": "Dihentikan"}}
