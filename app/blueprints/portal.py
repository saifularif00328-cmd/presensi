"""Portal Siswa & Orang Tua (/portal) — tampilan ramah HP, bisa dipasang sebagai aplikasi (PWA).

- Orang tua: masuk dengan nomor WhatsApp yang terdaftar di data siswa + kode OTP (WA).
  Satu nomor bisa melihat semua anaknya.
- Siswa: masuk dengan NIS + PIN dari sekolah (wajib ganti PIN saat pertama masuk).
- Hanya data anak/siswa sendiri yang bisa dilihat. Orang tua bisa mengajukan izin/sakit.
"""
import io
import os
import secrets
from datetime import timedelta
from functools import lru_cache, wraps

from flask import (Blueprint, abort, flash, redirect, render_template, request, send_file,
                   send_from_directory, session, url_for)
from PIL import Image, ImageDraw, ImageOps
from werkzeug.security import generate_password_hash

from .. import config, security, utils
from ..db import execute, get_db, get_setting, query
from ..services import portal as svc

bp = Blueprint("portal", __name__, url_prefix="/portal")

JENIS_IZIN = ("Izin", "Sakit")
KODE_LABEL = {"H": "Hadir", "T": "Telat", "I": "Izin", "S": "Sakit", "A": "Alpha",
              "D": "Dispensasi", "L": "Libur", "-": "Tidak ada data"}


def _aktif():
    return get_setting("portal_aktif") != "0"


def portal_login(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not _aktif():
            return render_template("portal/nonaktif.html"), 503
        p = session.get("portal")
        if not p:
            return redirect(url_for("portal.masuk"))
        if p["jenis"] == "siswa":
            s = query("SELECT pin_wajib_ganti, aktif FROM siswa WHERE id = ?", (p["siswa_id"],),
                      one=True)
            if s is None or not s["aktif"]:
                session.pop("portal", None)
                return redirect(url_for("portal.masuk"))
            if s["pin_wajib_ganti"] and request.endpoint != "portal.ganti_pin":
                return redirect(url_for("portal.ganti_pin"))
        return view(*a, **kw)
    return wrapped


def daftar_anak():
    """Siswa yang boleh dilihat oleh pengguna portal saat ini."""
    p = session.get("portal") or {}
    if p.get("jenis") == "ortu":
        return svc.anak_dari_nomor(p.get("nomor"))
    if p.get("jenis") == "siswa":
        return query("SELECT s.*, k.nama AS kelas_nama FROM siswa s LEFT JOIN kelas k "
                     "ON k.id = s.kelas_id WHERE s.id = ? AND s.aktif = 1", (p["siswa_id"],))
    return []


def _pilih_anak(sid=None):
    anak = daftar_anak()
    if not anak:
        return None, anak
    if sid is None:
        return anak[0], anak
    pilih = next((a for a in anak if a["id"] == sid), None)
    if pilih is None:
        abort(404)  # bukan anaknya
    return pilih, anak


# ================================================================ MASUK / KELUAR
@bp.route("/masuk", methods=["GET", "POST"])
def masuk():
    if not _aktif():
        return render_template("portal/nonaktif.html"), 503
    if session.get("portal"):
        return redirect(url_for("portal.beranda"))
    tab = request.args.get("sebagai", "ortu")
    nomor = ""
    tahap = "nomor"
    if request.method == "POST":
        aksi = request.form.get("aksi")
        ip = request.remote_addr or ""
        if aksi == "otp":
            nomor = request.form.get("nomor", "").strip()
            if security.terkunci("otp:" + utils.normalize_wa(nomor), ip):
                flash("Terlalu banyak percobaan. Coba lagi nanti.", "error")
            else:
                ok, pesan = svc.kirim_otp(nomor, ip, get_db())
                flash(pesan, "info" if ok else "error")
                if ok:
                    tahap = "kode"
        elif aksi == "verifikasi":
            nomor = request.form.get("nomor", "").strip()
            kunci = "otp:" + utils.normalize_wa(nomor)
            if security.terkunci(kunci, ip):
                flash("Terlalu banyak percobaan. Coba lagi nanti.", "error")
                tahap = "kode"
            else:
                n, err = svc.cek_otp(nomor, request.form.get("kode"), get_db())
                if n and svc.anak_dari_nomor(n):
                    security.reset_gagal(kunci)
                    session.pop("portal", None)
                    session["portal"] = {"jenis": "ortu", "nomor": n}
                    session.permanent = True
                    return redirect(url_for("portal.beranda"))
                security.catat_gagal(kunci, ip)
                flash(err or "Nomor tidak terdaftar sebagai orang tua/wali siswa.", "error")
                tahap = "kode"
        elif aksi == "siswa":
            tab = "siswa"
            nis = request.form.get("nis", "").strip()
            kunci = "siswa:" + nis
            if security.terkunci(kunci, ip):
                flash("Terlalu banyak percobaan. Coba lagi 15 menit lagi.", "error")
            else:
                s, err = svc.cek_pin(nis, request.form.get("pin"), get_db())
                if s:
                    security.reset_gagal(kunci)
                    session["portal"] = {"jenis": "siswa", "siswa_id": s["id"]}
                    session.permanent = True
                    return redirect(url_for("portal.beranda"))
                security.catat_gagal(kunci, ip)
                flash(err, "error")
    return render_template("portal/masuk.html", tab=tab, tahap=tahap, nomor=nomor)


@bp.route("/keluar")
def keluar():
    session.pop("portal", None)
    return redirect(url_for("portal.masuk"))


@bp.route("/ganti-pin", methods=["GET", "POST"])
@portal_login
def ganti_pin():
    p = session["portal"]
    if p["jenis"] != "siswa":
        return redirect(url_for("portal.beranda"))
    if request.method == "POST":
        pin = request.form.get("pin", "")
        if not pin.isdigit() or len(pin) != 6:
            flash("PIN harus 6 angka.", "error")
        elif pin != request.form.get("ulang"):
            flash("Konfirmasi PIN tidak sama.", "error")
        elif len(set(pin)) == 1 or pin in ("123456", "654321"):
            flash("PIN terlalu mudah ditebak.", "error")
        else:
            execute("UPDATE siswa SET pin_hash = ?, pin_wajib_ganti = 0 WHERE id = ?",
                    (generate_password_hash(pin), p["siswa_id"]))
            flash("PIN berhasil diganti.", "success")
            return redirect(url_for("portal.beranda"))
    return render_template("portal/ganti_pin.html")


# ================================================================ BERANDA & DETAIL
@bp.route("/")
@portal_login
def beranda():
    anak = daftar_anak()
    if len(anak) == 1:
        return redirect(url_for("portal.siswa", sid=anak[0]["id"]))
    tgl = utils.today_str()
    for a in anak:
        a["hari_ini"] = query("SELECT * FROM presensi WHERE siswa_id = ? AND tanggal = ?",
                              (a["id"], tgl), one=True)
    return render_template("portal/beranda.html", anak=anak)


@bp.route("/siswa/<int:sid>")
@portal_login
def siswa(sid):
    s, anak = _pilih_anak(sid)
    bulan = None
    b = request.args.get("bulan", "")
    if len(b) == 7 and b[4] == "-" and b[:4].isdigit() and b[5:].isdigit() and 1 <= int(b[5:]) <= 12:
        bulan = (int(b[:4]), int(b[5:]))
    data = svc.ringkasan(s["id"], get_db(), bulan)
    awal = data["awal"]
    sebelum = (awal - timedelta(days=1)).strftime("%Y-%m")
    sesudah = (awal + timedelta(days=32)).strftime("%Y-%m")
    from ..services.attendance import metode_aktif
    return render_template("portal/siswa.html", anak=anak, KODE=KODE_LABEL, sebelum=sebelum,
                           absen_hp=session["portal"]["jenis"] == "siswa" and metode_aktif("hp"),
                           sesudah=sesudah if sesudah <= utils.today().strftime("%Y-%m") else None,
                           ortu=session["portal"]["jenis"] == "ortu", **data)


@bp.route("/siswa/<int:sid>/izin", methods=["GET", "POST"])
@portal_login
def izin(sid):
    if session["portal"]["jenis"] != "ortu":
        abort(403)  # pengajuan izin hanya oleh orang tua/wali
    s, _anak = _pilih_anak(sid)
    if request.method == "POST":
        jenis = request.form.get("jenis")
        mulai = utils.parse_date(request.form.get("tanggal_mulai"))
        selesai = utils.parse_date(request.form.get("tanggal_selesai")) or mulai
        alasan = request.form.get("alasan", "").strip()
        today = utils.today()
        if jenis not in JENIS_IZIN or not mulai or selesai < mulai or not alasan:
            flash("Lengkapi jenis, tanggal, dan alasan dengan benar.", "error")
        elif mulai < today - timedelta(days=7) or selesai > today + timedelta(days=30):
            flash("Tanggal izin paling lama 7 hari ke belakang dan 30 hari ke depan.", "error")
        else:
            lampiran = _simpan_surat(request.files.get("surat"), s["id"])
            execute("INSERT INTO izin(siswa_id, jenis, tanggal_mulai, tanggal_selesai, alasan, "
                    "lampiran, pengaju) VALUES (?,?,?,?,?,?,?)",
                    (s["id"], jenis, mulai.isoformat(), selesai.isoformat(), alasan[:500],
                     lampiran, f"Orang tua (portal) {session['portal']['nomor']}"))
            flash("Pengajuan terkirim dan menunggu persetujuan sekolah.", "success")
            return redirect(url_for("portal.siswa", sid=s["id"]))
    return render_template("portal/izin.html", s=s, jenis=JENIS_IZIN)


def _simpan_surat(f, sid):
    if not f or not f.filename:
        return None
    try:
        img = ImageOps.exif_transpose(Image.open(f.stream)).convert("RGB")
    except Exception:
        return None
    img.thumbnail((1600, 1600))
    os.makedirs(os.path.join(config.UPLOAD_DIR, "surat"), exist_ok=True)
    name = f"surat/izin_{sid}_{secrets.token_hex(4)}.jpg"
    img.save(os.path.join(config.UPLOAD_DIR, name), "JPEG", quality=82)
    return name


# ================================================================ ABSEN DARI HP (siswa)
def _siswa_portal():
    p = session.get("portal") or {}
    if p.get("jenis") != "siswa":
        abort(403)            # absen HP hanya oleh siswa sendiri (bukan orang tua)
    return p["siswa_id"]


@bp.route("/absen")
@portal_login
def absen():
    from ..services import absen_hp
    sid = _siswa_portal()
    s = absen_hp.siswa_lengkap(sid)
    ok, alasan, lokasi = absen_hp.boleh(s)
    hari_ini = query("SELECT * FROM presensi WHERE siswa_id = ? AND tanggal = ?",
                     (sid, utils.today_str()), one=True)
    return render_template("portal/absen.html", s=s, boleh=ok, alasan=alasan, lokasi=lokasi,
                           hari_ini=hari_ini, libur=not utils.is_school_day(utils.today()))


@bp.route("/absen/token", methods=["POST"])
@portal_login
def absen_token():
    from flask import jsonify

    from ..services import absen_hp
    sid = _siswa_portal()
    ok, alasan, _ = absen_hp.boleh(absen_hp.siswa_lengkap(sid))
    if not ok:
        return jsonify({"ok": False, "pesan": alasan}), 403
    return jsonify({"ok": True, "token": absen_hp.buat_token(sid), "berlaku": absen_hp.TOKEN_DETIK})


@bp.route("/absen/kirim", methods=["POST"])
@portal_login
def absen_kirim():
    from flask import jsonify

    from ..services import absen_hp
    sid = _siswa_portal()
    res = absen_hp.proses(sid, request.form, request.files.get("foto"), ip=request.remote_addr or "",
                          ua=request.headers.get("User-Agent", ""))
    return jsonify({k: v for k, v in res.items() if k in ("ok", "level", "pesan", "jenis", "status",
                                                          "jam", "lokasi", "jarak")})


@bp.route("/foto/<int:sid>")
@portal_login
def foto(sid):
    s, _ = _pilih_anak(sid)
    if not s["foto"]:
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, s["foto"])


# ================================================================ PWA
@lru_cache(maxsize=4)
def _ikon_png(ukuran):
    """Ikon aplikasi (papan klip + centang, warna utama) digambar sekali lalu di-cache."""
    s = ukuran * 4
    img = Image.new("RGBA", (s, s), (29, 78, 216, 255))
    d = ImageDraw.Draw(img)
    w, h = s * 0.46, s * 0.56
    x0, y0 = (s - w) / 2, s * 0.24
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=s * 0.05, outline="white",
                        width=int(s * 0.045))
    cw = w * 0.5
    d.rounded_rectangle([(s - cw) / 2, y0 - s * 0.05, (s + cw) / 2, y0 + s * 0.06],
                        radius=s * 0.03, fill="white")
    d.line([(s * 0.40, s * 0.53), (s * 0.47, s * 0.60), (s * 0.61, s * 0.45)], fill="white",
           width=int(s * 0.05), joint="curve")
    buf = io.BytesIO()
    img.resize((ukuran, ukuran), Image.LANCZOS).save(buf, "PNG")
    return buf.getvalue()


@bp.route("/ikon-<int:ukuran>.png")
def ikon(ukuran):
    if ukuran not in (180, 192, 512):
        abort(404)
    return send_file(io.BytesIO(_ikon_png(ukuran)), mimetype="image/png", max_age=86400)


@bp.route("/manifest.webmanifest")
def manifest():
    nama = get_setting("nama_sekolah")
    return {"name": f"Presensi {nama}", "short_name": "Presensi", "start_url": url_for("portal.beranda"),
            "scope": url_for("portal.beranda"), "display": "standalone",
            "background_color": "#f5f6f8", "theme_color": "#1d4ed8", "lang": "id",
            "icons": [{"src": url_for("portal.ikon", ukuran=192), "sizes": "192x192",
                       "type": "image/png"},
                      {"src": url_for("portal.ikon", ukuran=512), "sizes": "512x512",
                       "type": "image/png", "purpose": "any maskable"}]}, 200, {
        "Content-Type": "application/manifest+json"}


@bp.route("/sw.js")
def service_worker():
    """Service worker sederhana: hanya menyimpan tampilan dasar agar ada halaman 'offline'."""
    js = render_template("portal/sw.js")
    return js, 200, {"Content-Type": "application/javascript", "Cache-Control": "no-cache"}
