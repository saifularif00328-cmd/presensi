"""Perizinan: Izin & Sakit, Izin Keluar, Pengajuan Kartu."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import utils
from ..auth import feature, roles
from ..db import execute, get_db, new_qr_token, query
from ..services import notify
from ..services.attendance import apply_izin
from .common import arg_int, form_int, kelas_options, siswa_options, valid_time

bp = Blueprint("perizinan", __name__, url_prefix="/perizinan")

JENIS_IZIN = ["Izin", "Sakit", "Dispensasi"]
ALASAN_KARTU = ["Hilang", "Rusak", "Lainnya"]


# ================================================================ IZIN & SAKIT
@bp.route("/izin", methods=["GET", "POST"])
@roles("piket", "bk")
@feature("perizinan")
def izin():
    if request.method == "POST":
        sid = form_int("siswa_id")
        jenis = request.form.get("jenis")
        mulai = utils.parse_date(request.form.get("tanggal_mulai"))
        selesai = utils.parse_date(request.form.get("tanggal_selesai")) or mulai
        if not sid or jenis not in JENIS_IZIN or not mulai or selesai < mulai:
            flash("Lengkapi siswa, jenis, dan tanggal dengan benar.", "error")
        else:
            execute("INSERT INTO izin(siswa_id, jenis, tanggal_mulai, tanggal_selesai, alasan, "
                    "diajukan_oleh) VALUES (?,?,?,?,?,?)",
                    (sid, jenis, mulai.isoformat(), selesai.isoformat(),
                     request.form.get("alasan", "").strip(), g.user["id"]))
            flash("Pengajuan izin dicatat dan menunggu persetujuan.", "success")
        return redirect(url_for("perizinan.izin"))
    status = request.args.get("status", "Menunggu")
    where, args = "", []
    if status in ("Menunggu", "Disetujui", "Ditolak"):
        where, args = "WHERE i.status = ?", [status]
    rows = query("SELECT i.*, s.nama, k.nama AS kelas, u.nama AS pengaju, v.nama AS pemroses "
                 "FROM izin i JOIN siswa s ON s.id = i.siswa_id LEFT JOIN kelas k ON "
                 "k.id = s.kelas_id LEFT JOIN users u ON u.id = i.diajukan_oleh LEFT JOIN users v "
                 f"ON v.id = i.diproses_oleh {where} ORDER BY i.id DESC LIMIT 300", args)
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM izin "
                                                  "GROUP BY status")}
    return render_template("perizinan/izin.html", rows=rows, status=status, counts=counts,
                           siswa=siswa_options(), jenis=JENIS_IZIN)


@bp.route("/izin/<int:iid>/<aksi>", methods=["POST"])
@roles("piket", "bk")
@feature("perizinan")
def izin_proses(iid, aksi):
    if aksi not in ("setujui", "tolak"):
        abort(404)
    db = get_db()
    row = query("SELECT * FROM izin WHERE id = ?", (iid,), one=True, db=db) or abort(404)
    if row["status"] != "Menunggu":
        flash("Pengajuan ini sudah diproses.", "error")
        return redirect(url_for("perizinan.izin"))
    status = "Disetujui" if aksi == "setujui" else "Ditolak"
    execute("UPDATE izin SET status = ?, diproses_oleh = ?, catatan_proses = ?, "
            "processed_at = datetime('now','localtime') WHERE id = ?",
            (status, g.user["id"], request.form.get("catatan", "").strip() or None, iid),
            db=db, commit=False)
    if status == "Disetujui":
        apply_izin(db, row)
        siswa = query("SELECT s.*, k.nama AS kelas_nama FROM siswa s LEFT JOIN kelas k "
                      "ON k.id = s.kelas_id WHERE s.id = ?", (row["siswa_id"],), one=True, db=db)
        rentang = row["tanggal_mulai"] if row["tanggal_mulai"] == row["tanggal_selesai"] \
            else f"{row['tanggal_mulai']} s.d. {row['tanggal_selesai']}"
        notify.enqueue(db, siswa, "izin", {"status": row["jenis"],
                                           "keterangan": f"Tanggal: {rentang}."})
    db.commit()
    flash(f"Pengajuan {status.lower()}.", "success")
    return redirect(url_for("perizinan.izin"))


@bp.route("/izin/<int:iid>/hapus", methods=["POST"])
@roles()
def izin_hapus(iid):
    execute("DELETE FROM izin WHERE id = ?", (iid,))
    flash("Data izin dihapus (data presensi yang sudah tercatat tidak berubah).", "success")
    return redirect(url_for("perizinan.izin", status="semua"))


# ================================================================ IZIN KELUAR
@bp.route("/keluar", methods=["GET", "POST"])
@roles("piket", "bk")
@feature("perizinan")
def keluar():
    if request.method == "POST":
        sid = form_int("siswa_id")
        jam = request.form.get("jam_keluar") or utils.now().strftime("%H:%M")
        alasan = request.form.get("alasan", "").strip()
        if not sid or not alasan or not valid_time(jam):
            flash("Siswa, jam keluar, dan alasan wajib diisi.", "error")
        else:
            execute("INSERT INTO izin_keluar(siswa_id, tanggal, jam_keluar, alasan, pencatat_id) "
                    "VALUES (?,?,?,?,?)", (sid, utils.today_str(), jam[:5], alasan, g.user["id"]))
            flash("Izin keluar dicatat.", "success")
        return redirect(url_for("perizinan.keluar"))
    tgl = utils.parse_date(request.args.get("tanggal"), utils.today())
    rows = query("SELECT i.*, s.nama, k.nama AS kelas, u.nama AS pencatat FROM izin_keluar i "
                 "JOIN siswa s ON s.id = i.siswa_id LEFT JOIN kelas k ON k.id = s.kelas_id "
                 "LEFT JOIN users u ON u.id = i.pencatat_id WHERE i.tanggal = ? "
                 "ORDER BY i.jam_keluar DESC", (tgl.isoformat(),))
    return render_template("perizinan/keluar.html", rows=rows, tgl=tgl, siswa=siswa_options(),
                           jam=utils.now().strftime("%H:%M"))


@bp.route("/keluar/<int:kid>/kembali", methods=["POST"])
@roles("piket", "bk")
@feature("perizinan")
def keluar_kembali(kid):
    execute("UPDATE izin_keluar SET jam_kembali = ? WHERE id = ? AND jam_kembali IS NULL",
            (utils.now().strftime("%H:%M"), kid))
    flash("Siswa ditandai sudah kembali.", "success")
    return redirect(request.referrer or url_for("perizinan.keluar"))


# ================================================================ PENGAJUAN KARTU
@bp.route("/kartu", methods=["GET", "POST"])
@roles("piket")
@feature("perizinan")
def kartu():
    if request.method == "POST":
        sid = form_int("siswa_id")
        alasan = request.form.get("alasan")
        if not sid or alasan not in ALASAN_KARTU:
            flash("Pilih siswa dan alasan pengajuan.", "error")
        else:
            execute("INSERT INTO pengajuan_kartu(siswa_id, alasan, keterangan) VALUES (?,?,?)",
                    (sid, alasan, request.form.get("keterangan", "").strip() or None))
            flash("Pengajuan cetak ulang kartu dicatat (status: Diproses).", "success")
        return redirect(url_for("perizinan.kartu"))
    rows = query("SELECT p.*, s.nama, k.nama AS kelas FROM pengajuan_kartu p "
                 "JOIN siswa s ON s.id = p.siswa_id LEFT JOIN kelas k ON k.id = s.kelas_id "
                 "ORDER BY p.status = 'Selesai', p.id DESC LIMIT 300")
    return render_template("perizinan/kartu.html", rows=rows, siswa=siswa_options(),
                           alasan=ALASAN_KARTU, kelas=kelas_options())


@bp.route("/kartu/<int:pid>/selesai", methods=["POST"])
@roles()
@feature("perizinan")
def kartu_selesai(pid):
    """Tandai selesai. Untuk kartu hilang, QR diganti agar kartu lama tak bisa dipakai."""
    db = get_db()
    p = query("SELECT * FROM pengajuan_kartu WHERE id = ?", (pid,), one=True, db=db) or abort(404)
    if request.form.get("ganti_qr"):
        execute("UPDATE siswa SET qr_token = ? WHERE id = ?", (new_qr_token(), p["siswa_id"]),
                db=db, commit=False)
    execute("UPDATE pengajuan_kartu SET status = 'Selesai', "
            "selesai_at = datetime('now','localtime') WHERE id = ?", (pid,), db=db)
    flash("Pengajuan selesai. Silakan cetak kartu baru.", "success")
    return redirect(url_for("perizinan.kartu", cetak=p["siswa_id"]))


@bp.route("/kartu/<int:pid>/hapus", methods=["POST"])
@roles()
def kartu_hapus(pid):
    execute("DELETE FROM pengajuan_kartu WHERE id = ?", (pid,))
    return redirect(url_for("perizinan.kartu"))


@bp.route("/kelas-siswa")
@roles("piket", "bk")
def kelas_siswa():
    """Helper JSON: daftar siswa per kelas untuk dropdown."""
    from flask import jsonify
    return jsonify([dict(r) for r in siswa_options(arg_int("kelas_id"))])
