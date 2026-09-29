"""Sistem: Kalender Libur, Akses User, Info, Pengaturan, Lisensi, Multi-Cabang, Backup."""
import hmac
import io
import os
import secrets

import requests
from PIL import Image
from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, url_for)
from werkzeug.security import generate_password_hash

from .. import config, utils
from ..auth import ROLES, feature, roles
from ..db import IntegrityError, execute, get_db, get_setting, query, set_setting
from ..license import current_license, device_id, public_key
from ..services import lisensi as lisensi_svc
from ..services.rekap import rekap_kelas_hari
from .common import arg_int, form_int

bp = Blueprint("sistem", __name__, url_prefix="/sistem")


# ================================================================ KALENDER LIBUR
@bp.route("/libur", methods=["GET", "POST"])
@roles()
@feature("presensi")
def libur():
    if request.method == "POST":
        mulai = utils.parse_date(request.form.get("tanggal"))
        selesai = utils.parse_date(request.form.get("sampai")) or mulai
        ket = request.form.get("keterangan", "").strip()
        if not mulai or not ket or selesai < mulai:
            flash("Tanggal dan keterangan wajib diisi.", "error")
        else:
            n = 0
            for d in utils.daterange(mulai, selesai):
                execute("INSERT INTO libur(tanggal, keterangan) VALUES (?, ?) ON DUPLICATE KEY "
                        "UPDATE keterangan = VALUES(keterangan)", (d.isoformat(), ket),
                        commit=False)
                n += 1
            get_db().commit()
            flash(f"{n} tanggal libur disimpan. Presensi otomatis dilewati pada tanggal "
                  "tersebut.", "success")
        return redirect(url_for("sistem.libur"))
    tahun = arg_int("tahun", utils.today().year)
    rows = query("SELECT * FROM libur WHERE YEAR(tanggal) = ? ORDER BY tanggal",
                 (str(tahun),))
    return render_template("sistem/libur.html", rows=rows, tahun=tahun,
                           hari_sekolah=utils.hari_sekolah(), HARI=utils.HARI)


@bp.route("/libur/<int:lid>/hapus", methods=["POST"])
@roles()
def libur_hapus(lid):
    execute("DELETE FROM libur WHERE id = ?", (lid,))
    return redirect(request.referrer or url_for("sistem.libur"))


# ================================================================ AKSES USER
@bp.route("/users", methods=["GET", "POST"])
@roles()
@feature("multiuser")
def users():
    if request.method == "POST":
        uid = form_int("id")
        username = request.form.get("username", "").strip().lower()
        nama = request.form.get("nama", "").strip()
        role = request.form.get("role")
        pw = request.form.get("password", "")
        if not username or not nama or role not in ROLES or (not uid and len(pw) < 6):
            flash("Lengkapi data. Password minimal 6 karakter untuk user baru.", "error")
            return redirect(url_for("sistem.users"))
        if uid == g.user["id"] and role != "admin":
            flash("Anda tidak bisa menurunkan role akun sendiri.", "error")
            return redirect(url_for("sistem.users"))
        aktif = 1 if request.form.get("aktif") or uid == g.user["id"] else 0
        try:
            if uid:
                execute("UPDATE users SET username = ?, nama = ?, role = ?, guru_id = ?, aktif = ? "
                        "WHERE id = ?", (username, nama, role, form_int("guru_id"), aktif, uid))
                if pw:
                    if len(pw) < 6:
                        flash("Password minimal 6 karakter.", "error")
                        return redirect(url_for("sistem.users", edit=uid))
                    # password diset admin = sementara; pengguna wajib menggantinya
                    execute("UPDATE users SET password_hash = ?, wajib_ganti = 1 WHERE id = ?",
                            (generate_password_hash(pw), uid))
            else:
                execute("INSERT INTO users(username, password_hash, nama, role, guru_id, aktif, "
                        "wajib_ganti) VALUES (?,?,?,?,?,?, 1)", (username, generate_password_hash(pw), nama, role,
                                                 form_int("guru_id"), aktif))
            flash("User disimpan.", "success")
        except IntegrityError:
            flash(f"Username '{username}' sudah dipakai.", "error")
        return redirect(url_for("sistem.users"))
    rows = query("SELECT u.*, gu.nama AS guru FROM users u LEFT JOIN guru gu ON gu.id = u.guru_id "
                 "ORDER BY u.role, u.nama")
    edit = query("SELECT * FROM users WHERE id = ?", (arg_int("edit"),), one=True)
    guru = query("SELECT id, nama, jabatan FROM guru WHERE aktif = 1 ORDER BY nama")
    return render_template("sistem/users.html", rows=rows, edit=edit, guru=guru)


@bp.route("/users/<int:uid>/hapus", methods=["POST"])
@roles()
def users_hapus(uid):
    if uid == g.user["id"]:
        flash("Tidak bisa menghapus akun sendiri.", "error")
    else:
        execute("DELETE FROM users WHERE id = ?", (uid,))
        flash("User dihapus.", "success")
    return redirect(url_for("sistem.users"))


# ================================================================ INFO
@bp.route("/info", methods=["GET", "POST"])
@roles("piket", "bk")
@feature("presensi")
def info():
    if request.method == "POST":
        if g.user["role"] != "admin":
            abort(403)
        judul, isi = request.form.get("judul", "").strip(), request.form.get("isi", "").strip()
        if not judul or not isi:
            flash("Judul dan isi wajib diisi.", "error")
            return redirect(url_for("sistem.info"))
        iid = form_int("id")
        vals = (judul, isi, 1 if request.form.get("penting") else 0,
                1 if request.form.get("aktif") else 0)
        if iid:
            execute("UPDATE info SET judul = ?, isi = ?, penting = ?, aktif = ? WHERE id = ?",
                    vals + (iid,))
        else:
            execute("INSERT INTO info(judul, isi, penting, aktif, pembuat_id) VALUES (?,?,?,?,?)",
                    vals + (g.user["id"],))
        flash("Pengumuman disimpan.", "success")
        return redirect(url_for("sistem.info"))
    where = "" if g.user["role"] == "admin" else "WHERE i.aktif = 1"
    rows = query("SELECT i.*, u.nama AS pembuat FROM info i LEFT JOIN users u ON "
                 f"u.id = i.pembuat_id {where} ORDER BY i.penting DESC, i.id DESC")
    edit = query("SELECT * FROM info WHERE id = ?", (arg_int("edit"),), one=True)
    return render_template("sistem/info.html", rows=rows, edit=edit)


@bp.route("/info/<int:iid>/hapus", methods=["POST"])
@roles()
def info_hapus(iid):
    execute("DELETE FROM info WHERE id = ?", (iid,))
    return redirect(url_for("sistem.info"))


# ================================================================ PENGATURAN
@bp.route("/pengaturan", methods=["GET", "POST"])
@roles()
def pengaturan():
    if request.method == "POST":
        db = get_db()
        for k in PROFIL_KEYS:
            if k in request.form:
                set_setting(k, request.form.get(k, "").strip(), db=db, commit=False)
        hari = [h for h in request.form.getlist("hari_sekolah") if h.isdigit()]
        set_setting("hari_sekolah", ",".join(hari) or "1,2,3,4,5", db=db, commit=False)
        zona = request.form.get("zona_waktu")
        if zona in utils.ZONA:
            set_setting("zona_waktu", zona, db=db, commit=False)
        set_setting("modul_ibadah_aktif", "1" if request.form.get("modul_ibadah_aktif") else "0",
                    db=db, commit=False)
        set_setting("portal_aktif", "1" if request.form.get("portal_aktif") else "0",
                    db=db, commit=False)
        _simpan_gambar(db, "logo", "logo_sekolah", "logo_sekolah", (512, 512))
        _simpan_gambar(db, "ttd", "ttd_kepsek", "ttd_kepsek", (900, 400))
        r = request.form.get("monitor_refresh_detik", "3")
        set_setting("monitor_refresh_detik", r if r.isdigit() and 1 <= int(r) <= 60 else "3",
                    db=db, commit=False)
        db.commit()
        flash("Pengaturan disimpan.", "success")
        return redirect(url_for("sistem.pengaturan"))
    backups = []
    if os.path.isdir(config.BACKUP_DIR):
        backups = sorted((f for f in os.listdir(config.BACKUP_DIR) if f.endswith((".db", ".zip"))),
                         reverse=True)
    return render_template("sistem/pengaturan.html", hari=utils.hari_sekolah(), HARI=utils.HARI,
                           backups=backups, data_dir=os.path.abspath(config.DATA_DIR),
                           alamat=get_setting("alamat_sekolah"),
                           prof={k: get_setting(k) for k in PROFIL_KEYS},
                           ttd_url=(url_for("uploads", filename=get_setting("ttd_kepsek"))
                                    if get_setting("ttd_kepsek") else None),
                           refresh=get_setting("monitor_refresh_detik"),
                           ZONA=utils.ZONA, zona=get_setting("zona_waktu"),
                           portal_aktif=get_setting("portal_aktif") != "0")


PROFIL_KEYS = ("nama_sekolah", "alamat_sekolah", "kota_sekolah", "telepon_sekolah", "email_sekolah",
               "website_sekolah", "npsn", "akreditasi", "kepala_sekolah", "nip_kepala", "visi",
               "misi", "kartu_ketentuan", "kartu_berlaku")


def _simpan_gambar(db, field, key, prefix, max_size):
    """Simpan gambar unggahan (logo / tanda tangan) sebagai PNG transparan."""
    old = get_setting(key, db=db)
    if request.form.get(f"hapus_{field}") and old:
        path = os.path.join(config.UPLOAD_DIR, old)
        if os.path.exists(path):
            os.remove(path)
        set_setting(key, "", db=db, commit=False)
        return
    f = request.files.get(field)
    if not f or not f.filename:
        return
    try:
        img = Image.open(f.stream).convert("RGBA")
    except Exception:
        flash("File gambar tidak valid (gunakan PNG/JPG).", "error")
        return
    img.thumbnail(max_size)
    name = f"{prefix}_{secrets.token_hex(3)}.png"
    img.save(os.path.join(config.UPLOAD_DIR, name), "PNG")
    if old and os.path.exists(os.path.join(config.UPLOAD_DIR, old)):
        os.remove(os.path.join(config.UPLOAD_DIR, old))
    set_setting(key, name, db=db, commit=False)


@bp.route("/backup")
@roles()
def backup():
    """Unduh backup lengkap (database + foto + kunci) dalam satu file ZIP."""
    from ..services.backup import make_zip
    return send_file(io.BytesIO(make_zip(get_db())), as_attachment=True,
                     mimetype="application/zip",
                     download_name=f"presensi-backup-{utils.now():%Y%m%d-%H%M}.zip")


# ================================================================ LISENSI
@bp.route("/lisensi", methods=["GET", "POST"])
@roles()
def lisensi():
    if request.method == "POST":
        db = get_db()
        if request.form.get("aksi") == "online":
            ok, res = lisensi_svc.activate_online(db, request.form.get("server", ""),
                                                  request.form.get("kode", ""))
            if ok:
                flash("Langganan aktif"
                      f"{' sampai ' + res['exp'] if res['exp'] else ' tanpa batas waktu'}.", "success")
            else:
                flash(res, "error")
        elif request.form.get("aksi") == "cek":
            st = lisensi_svc.check_online(db)
            flash({"aktif": "Lisensi terverifikasi aktif di server.",
                   "dicabut": "Server menyatakan lisensi ini DICABUT."}.get(
                       st, "Tidak dapat mengecek ke server (offline / server belum diatur)."),
                  "success" if st == "aktif" else "error")
        else:
            info = lisensi_svc.activate_offline(db, request.form.get("license_key", ""))
            if info["valid"]:
                flash("Kode lisensi berhasil diaktifkan.", "success")
            else:
                flash(f"Kode lisensi ditolak: {info['reason']}", "error")
        return redirect(url_for("sistem.lisensi"))
    return render_template("sistem/lisensi.html", device=device_id(),
                           info=current_license(), key=get_setting("license_key"),
                           server=lisensi_svc.server_url(),
                           checked=get_setting("license_checked"),
                           pubkey_ok=public_key() is not None)


# ================================================================ AKSES ONLINE (Cloudflare Tunnel)
def _cloudflared():
    """Lokasi cloudflared.exe di samping aplikasi (server sekolah Windows), atau None."""
    import shutil
    import sys
    lokal = os.path.join(config.BASE_DIR, "cloudflared.exe" if sys.platform == "win32"
                         else "cloudflared")
    return lokal if os.path.exists(lokal) else shutil.which("cloudflared")


def _status_tunnel():
    import subprocess
    import sys
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "RUNNING" in out:
        return "berjalan"
    return "berhenti" if "STATE" in out else "belum"


@bp.route("/akses-online", methods=["GET", "POST"])
@roles()
def akses_online():
    """Hubungkan server sekolah ke internet lewat Cloudflare Tunnel (token dari penyedia)."""
    import re
    import subprocess
    exe = _cloudflared()
    if request.method == "POST":
        aksi = request.form.get("aksi")
        if aksi == "alamat":
            url = request.form.get("alamat_publik", "").strip().rstrip("/")
            if url and not re.match(r"^https://[a-z0-9.-]+$", url):
                flash("Alamat harus berbentuk https://nama.domain (tanpa garis miring di akhir).",
                      "error")
            else:
                set_setting("alamat_publik", url)
                flash("Alamat publik disimpan.", "success")
        elif aksi == "tunnel":
            token = re.sub(r"\s", "", request.form.get("token", ""))
            if token.lower().startswith("cloudflared"):  # tempelan perintah lengkap
                token = token.split("install")[-1]
            if not re.fullmatch(r"[A-Za-z0-9_\-=+/]{40,4000}", token):
                flash("Token tidak valid. Salin token dari penyedia (deretan huruf-angka panjang).",
                      "error")
            elif not exe:
                flash("cloudflared tidak ditemukan di komputer ini.", "error")
            else:
                try:
                    subprocess.run([exe, "service", "uninstall"], capture_output=True, timeout=60)
                    r = subprocess.run([exe, "service", "install", token], capture_output=True,
                                       text=True, timeout=120)
                    if r.returncode == 0:
                        flash("Terhubung ke Cloudflare. Portal bisa dibuka dari internet dalam "
                              "±1 menit.", "success")
                    else:
                        flash("Gagal memasang tunnel: " + (r.stderr or r.stdout)[-300:], "error")
                except (OSError, subprocess.SubprocessError) as e:
                    flash(f"Gagal menjalankan cloudflared: {e}", "error")
        return redirect(url_for("sistem.akses_online"))
    return render_template("sistem/akses_online.html", exe=exe, status=_status_tunnel(),
                           alamat=get_setting("alamat_publik") or "",
                           cloud=os.environ.get("PRESENSI_MODE") == "cloud",
                           lan=f"http://{utils.local_ip()}:{config.PORT}")


# ================================================================ MULTI-CABANG
@bp.route("/cabang", methods=["GET", "POST"])
@roles()
@feature("multicabang")
def cabang():
    if request.method == "POST":
        nama, url, token = (request.form.get(k, "").strip() for k in ("nama", "url", "token"))
        if not nama or not url.startswith(("http://", "https://")) or not token:
            flash("Nama, URL (http://...) dan token wajib diisi.", "error")
        else:
            execute("INSERT INTO cabang(nama, url, token) VALUES (?,?,?)",
                    (nama, url.rstrip("/"), token))
            flash("Cabang ditambahkan.", "success")
        return redirect(url_for("sistem.cabang"))
    rows = query("SELECT * FROM cabang ORDER BY nama")
    data = []
    for c in rows:
        try:
            r = requests.get(f"{c['url']}/sistem/api/ringkasan", timeout=4,
                             headers={"X-Cabang-Token": c["token"],
                                      "ngrok-skip-browser-warning": "1"})
            if r.status_code == 401:
                err = "token salah"
            elif not r.ok:
                err = f"HTTP {r.status_code} (periksa URL)"
            else:
                err = None
            data.append({"c": c, "ok": err is None, "d": r.json() if err is None else None,
                         "err": err})
        except ValueError:
            data.append({"c": c, "ok": False, "d": None,
                         "err": "alamat tersebut bukan server Presensi (periksa URL)"})
        except requests.Timeout:
            data.append({"c": c, "ok": False, "d": None,
                         "err": "tidak ada jawaban (server cabang mati / beda jaringan)"})
        except requests.RequestException:
            data.append({"c": c, "ok": False, "d": None,
                         "err": "tidak dapat terhubung (server cabang mati / URL salah)"})
    lokal = ringkasan_data()
    return render_template("sistem/cabang.html", data=data, lokal=lokal,
                           token=get_setting("cabang_api_token"),
                           url_lokal=f"http://{utils.local_ip()}:{config.PORT}")


@bp.route("/cabang/<int:cid>/hapus", methods=["POST"])
@roles()
def cabang_hapus(cid):
    execute("DELETE FROM cabang WHERE id = ?", (cid,))
    return redirect(url_for("sistem.cabang"))


def ringkasan_data():
    rekap = rekap_kelas_hari(get_db(), utils.today_str())
    tot = {k: sum(r[k] for r in rekap) for k in ("total", "H", "I", "S", "A", "D", "belum",
                                                   "telat")}
    return {"sekolah": get_setting("nama_sekolah"), "tanggal": utils.today_str(),
            "waktu": utils.now().strftime("%H:%M"), **tot}


@bp.route("/api/ringkasan")
def api_ringkasan():
    """Endpoint read-only untuk dashboard multi-cabang (autentikasi via token)."""
    token = request.headers.get("X-Cabang-Token", "")
    if not hmac.compare_digest(token, get_setting("cabang_api_token") or "x"):
        return jsonify({"error": "token tidak valid"}), 401
    return jsonify(ringkasan_data())
