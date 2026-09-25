"""Halaman utama: Beranda, Siswa (bottom nav), Akun."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .. import utils
from ..auth import login_required
from ..db import execute, get_db, get_setting, query
from ..license import has_feature
from ..qr import make_payload
from ..services.rekap import rekap_kelas_hari
from .common import arg_date, arg_int, kelas_options, send_export

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def beranda():
    tgl = arg_date("tanggal", utils.today())
    rekap = rekap_kelas_hari(get_db(), tgl.isoformat())
    total = {k: sum(r[k] for r in rekap) for k in ("total", "H", "I", "S", "A", "D", "belum",
                                                     "telat")}
    infos = query("SELECT * FROM info WHERE aktif = 1 ORDER BY penting DESC, id DESC LIMIT 3")
    wa = None
    if g.user["role"] == "admin" and has_feature("whatsapp"):
        wa = {
            "kuota": get_setting("fonnte_kuota"),
            "cek": get_setting("fonnte_kuota_cek"),
            "antri": query("SELECT COUNT(*) AS n FROM notif_queue WHERE status = "
                           "'Menunggu Koneksi'", one=True)["n"],
            "gagal": query("SELECT COUNT(*) AS n FROM notif_queue WHERE status = 'Gagal'",
                           one=True)["n"],
            "token": bool(get_setting("fonnte_token")),
        }
    libur = None if utils.is_school_day(tgl) else (utils.libur_on(tgl) or "Bukan hari sekolah")
    return render_template("beranda.html", rekap=rekap, total=total, tgl=tgl, infos=infos,
                           wa=wa, libur=libur)


@bp.route("/rekap-kelas/export")
@login_required
def rekap_kelas_export():
    tgl = arg_date("tanggal", utils.today())
    kelas_id = arg_int("kelas_id")
    fmt = request.args.get("format", "xlsx")
    if kelas_id:
        kelas = query("SELECT * FROM kelas WHERE id = ?", (kelas_id,), one=True) or abort(404)
        rows = query("SELECT s.nis, s.nama, p.keterangan, p.jam_masuk, p.status_masuk, "
                     "p.jam_pulang, p.status_pulang, p.catatan FROM siswa s "
                     "LEFT JOIN presensi p ON p.siswa_id = s.id AND p.tanggal = ? "
                     "WHERE s.kelas_id = ? AND s.aktif = 1 ORDER BY s.nama",
                     (tgl.isoformat(), kelas_id))
        data = [(i, r["nis"] or "", r["nama"], r["keterangan"] or "-",
                 (r["jam_masuk"] or "")[:5], r["status_masuk"] or "",
                 (r["jam_pulang"] or "")[:5], r["status_pulang"] or "", r["catatan"] or "")
                for i, r in enumerate(rows, 1)]
        return send_export(fmt, f"presensi-{kelas['nama']}-{tgl}",
                           f"Presensi Kelas {kelas['nama']}", ["No", "NIS", "Nama", "Ket",
                           "Masuk", "Status Masuk", "Pulang", "Status Pulang", "Catatan"],
                           data, utils.tanggal_indo(tgl))
    rekap = rekap_kelas_hari(get_db(), tgl.isoformat())
    data = [(r["nama"], r["total"], r["H"], r["telat"], r["I"], r["S"], r["A"], r["D"],
             r["belum"]) for r in rekap]
    return send_export(fmt, f"rekap-kelas-{tgl}", "Rekap Presensi Per Kelas",
                       ["Kelas", "Siswa", "H", "Telat", "I", "S", "A", "D", "Belum"], data,
                       f"{get_setting('nama_sekolah')} — {utils.tanggal_indo(tgl)}")


@bp.route("/siswa")
@login_required
def siswa():
    q = request.args.get("q", "").strip()
    kelas_id = arg_int("kelas_id")
    where, args = ["s.aktif = 1"], [utils.today_str()]
    if q:
        where.append("(s.nama LIKE ? OR s.nis LIKE ? OR s.nisn LIKE ?)")
        args += [f"%{q}%"] * 3
    if kelas_id:
        where.append("s.kelas_id = ?")
        args.append(kelas_id)
    rows = query("SELECT s.*, k.nama AS kelas_nama, p.keterangan, p.jam_masuk, p.status_masuk, "
                 "p.jam_pulang, p.status_pulang FROM siswa s "
                 "LEFT JOIN kelas k ON k.id = s.kelas_id "
                 "LEFT JOIN presensi p ON p.siswa_id = s.id AND p.tanggal = ? "
                 f"WHERE {' AND '.join(where)} ORDER BY k.nama, s.nama LIMIT 500", args)
    return render_template("siswa_list.html", rows=rows, q=q, kelas_id=kelas_id,
                           kelas=kelas_options())


@bp.route("/siswa/<int:sid>")
@login_required
def siswa_detail(sid):
    s = query("SELECT s.*, k.nama AS kelas_nama FROM siswa s LEFT JOIN kelas k "
              "ON k.id = s.kelas_id WHERE s.id = ?", (sid,), one=True) or abort(404)
    presensi = query("SELECT * FROM presensi WHERE siswa_id = ? ORDER BY tanggal DESC LIMIT 60",
                     (sid,))
    ringkas = query("SELECT keterangan, COUNT(*) AS n FROM presensi WHERE siswa_id = ? "
                    "GROUP BY keterangan", (sid,))
    izin = query("SELECT * FROM izin WHERE siswa_id = ? ORDER BY id DESC LIMIT 20", (sid,))
    keluar = query("SELECT * FROM izin_keluar WHERE siswa_id = ? ORDER BY id DESC LIMIT 20",
                   (sid,))
    pelanggaran = query("SELECT p.*, j.nama AS jenis FROM pelanggaran p LEFT JOIN "
                        "jenis_pelanggaran j ON j.id = p.jenis_id WHERE p.siswa_id = ? "
                        "ORDER BY p.tanggal DESC, p.id DESC", (sid,))
    poin = sum(p["poin"] for p in pelanggaran)
    return render_template("siswa_detail.html", s=s, presensi=presensi,
                           ringkas={r["keterangan"]: r["n"] for r in ringkas}, izin=izin,
                           keluar=keluar, pelanggaran=pelanggaran, poin=poin,
                           payload=make_payload(s["qr_token"]))


@bp.route("/akun", methods=["GET", "POST"])
@login_required
def akun():
    if request.method == "POST":
        lama = request.form.get("password_lama", "")
        baru = request.form.get("password_baru", "")
        if not check_password_hash(g.user["password_hash"], lama):
            flash("Password lama salah.", "error")
        elif len(baru) < 6:
            flash("Password baru minimal 6 karakter.", "error")
        elif baru != request.form.get("password_ulang", ""):
            flash("Konfirmasi password tidak sama.", "error")
        else:
            execute("UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(baru), g.user["id"]))
            flash("Password berhasil diganti.", "success")
        return redirect(url_for("main.akun"))
    guru = None
    if g.user["guru_id"]:
        guru = query("SELECT * FROM guru WHERE id = ?", (g.user["guru_id"],), one=True)
    return render_template("akun.html", guru=guru)
