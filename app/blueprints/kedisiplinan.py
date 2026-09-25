"""Kedisiplinan: Tata Tertib, Rekap Pelanggaran, Aturan Jam."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import utils
from ..auth import feature, roles
from ..db import execute, get_db, query
from ..services import notify
from .common import (arg_date, arg_int, form_int, kelas_options, send_export, siswa_options,
                     valid_time)

bp = Blueprint("kedisiplinan", __name__, url_prefix="/kedisiplinan")


# ================================================================ TATA TERTIB
@bp.route("/tata-tertib", methods=["GET", "POST"])
@roles("piket", "bk")
@feature("presensi")
def tatib():
    if request.method == "POST":
        if g.user["role"] not in ("admin", "bk"):
            flash("Hanya Admin / Guru BK yang dapat mengubah tata tertib.", "error")
            return redirect(url_for("kedisiplinan.tatib"))
        judul = request.form.get("judul", "").strip()
        if not judul:
            flash("Judul wajib diisi.", "error")
            return redirect(url_for("kedisiplinan.tatib"))
        vals = (judul, request.form.get("isi", "").strip(), form_int("urutan", 0))
        tid = form_int("id")
        if tid:
            execute("UPDATE tata_tertib SET judul = ?, isi = ?, urutan = ? WHERE id = ?",
                    vals + (tid,))
        else:
            execute("INSERT INTO tata_tertib(judul, isi, urutan) VALUES (?,?,?)", vals)
        flash("Tata tertib disimpan.", "success")
        return redirect(url_for("kedisiplinan.tatib"))
    rows = query("SELECT * FROM tata_tertib ORDER BY urutan, id")
    edit = query("SELECT * FROM tata_tertib WHERE id = ?", (arg_int("edit"),), one=True)
    jenis = query("SELECT * FROM jenis_pelanggaran ORDER BY poin")
    return render_template("kedisiplinan/tatib.html", rows=rows, edit=edit, jenis=jenis)


@bp.route("/tata-tertib/<int:tid>/hapus", methods=["POST"])
@roles("bk")
def tatib_hapus(tid):
    execute("DELETE FROM tata_tertib WHERE id = ?", (tid,))
    flash("Tata tertib dihapus.", "success")
    return redirect(url_for("kedisiplinan.tatib"))


# ================================================================ PELANGGARAN
@bp.route("/pelanggaran", methods=["GET", "POST"])
@roles("bk")
@feature("pelanggaran")
def pelanggaran():
    db = get_db()
    if request.method == "POST":
        sid, jid = form_int("siswa_id"), form_int("jenis_id")
        tgl = utils.parse_date(request.form.get("tanggal"), utils.today())
        jenis = query("SELECT * FROM jenis_pelanggaran WHERE id = ?", (jid,), one=True, db=db)
        if not sid or not jenis:
            flash("Pilih siswa dan jenis pelanggaran.", "error")
            return redirect(url_for("kedisiplinan.pelanggaran"))
        poin = form_int("poin", jenis["poin"])
        execute("INSERT INTO pelanggaran(siswa_id, jenis_id, tanggal, poin, keterangan, "
                "tindak_lanjut, pencatat_id) VALUES (?,?,?,?,?,?,?)",
                (sid, jid, tgl.isoformat(), poin, request.form.get("keterangan", "").strip(),
                 request.form.get("tindak_lanjut", "").strip(), g.user["id"]), db=db,
                commit=False)
        if jenis["notif_aktif"]:
            siswa = query("SELECT s.*, k.nama AS kelas_nama FROM siswa s LEFT JOIN kelas k "
                          "ON k.id = s.kelas_id WHERE s.id = ?", (sid,), one=True, db=db)
            notify.enqueue(db, siswa, "pelanggaran",
                           {"status": jenis["nama"], "jam": utils.tanggal_indo(tgl),
                            "keterangan": request.form.get("keterangan", "").strip()})
        db.commit()
        flash("Pelanggaran dicatat.", "success")
        return redirect(url_for("kedisiplinan.pelanggaran"))

    tab = request.args.get("tab", "catatan")
    dari = arg_date("dari", utils.today().replace(day=1))
    sampai = arg_date("sampai", utils.today())
    kelas_id = arg_int("kelas_id")
    kf, args = "", [dari.isoformat(), sampai.isoformat()]
    if kelas_id:
        kf = " AND s.kelas_id = ?"
        args.append(kelas_id)
    catatan = query("SELECT p.*, s.nama, k.nama AS kelas, j.nama AS jenis, j.kategori, "
                    "u.nama AS pencatat FROM pelanggaran p JOIN siswa s ON s.id = p.siswa_id "
                    "LEFT JOIN kelas k ON k.id = s.kelas_id LEFT JOIN jenis_pelanggaran j ON "
                    "j.id = p.jenis_id LEFT JOIN users u ON u.id = p.pencatat_id "
                    f"WHERE p.tanggal BETWEEN ? AND ?{kf} ORDER BY p.tanggal DESC, p.id DESC",
                    args, db=db)
    per_siswa = query("SELECT s.id, s.nis, s.nama, k.nama AS kelas, COUNT(p.id) AS jumlah, "
                      "SUM(p.poin) AS poin FROM pelanggaran p JOIN siswa s ON s.id = p.siswa_id "
                      "LEFT JOIN kelas k ON k.id = s.kelas_id WHERE p.tanggal BETWEEN ? AND ?"
                      f"{kf} GROUP BY s.id ORDER BY poin DESC", args, db=db)
    fmt = request.args.get("format")
    if fmt in ("xlsx", "pdf"):
        if tab == "siswa":
            data = [(i, r["nis"] or "", r["nama"], r["kelas"] or "", r["jumlah"], r["poin"])
                    for i, r in enumerate(per_siswa, 1)]
            return send_export(fmt, f"rekap-poin-{dari}-{sampai}", "Rekap Poin Pelanggaran",
                               ["No", "NIS", "Nama", "Kelas", "Jumlah", "Total Poin"], data,
                               f"{dari} s.d. {sampai}")
        data = [(r["tanggal"], r["nama"], r["kelas"] or "", r["jenis"] or "-", r["poin"],
                 r["keterangan"] or "", r["tindak_lanjut"] or "", r["pencatat"] or "")
                for r in catatan]
        return send_export(fmt, f"pelanggaran-{dari}-{sampai}", "Rekap Pelanggaran",
                           ["Tanggal", "Nama", "Kelas", "Jenis", "Poin", "Keterangan",
                            "Tindak Lanjut", "Pencatat"], data, f"{dari} s.d. {sampai}")
    jenis = query("SELECT * FROM jenis_pelanggaran ORDER BY kategori, nama", db=db)
    return render_template("kedisiplinan/pelanggaran.html", catatan=catatan,
                           per_siswa=per_siswa, jenis=jenis, siswa=siswa_options(),
                           kelas=kelas_options(), kelas_id=kelas_id, dari=dari, sampai=sampai,
                           tab=tab)


@bp.route("/pelanggaran/<int:pid>/tindak-lanjut", methods=["POST"])
@roles("bk")
@feature("pelanggaran")
def pelanggaran_tl(pid):
    execute("UPDATE pelanggaran SET tindak_lanjut = ? WHERE id = ?",
            (request.form.get("tindak_lanjut", "").strip(), pid))
    flash("Tindak lanjut diperbarui.", "success")
    return redirect(request.referrer or url_for("kedisiplinan.pelanggaran"))


@bp.route("/pelanggaran/<int:pid>/hapus", methods=["POST"])
@roles("bk")
def pelanggaran_hapus(pid):
    execute("DELETE FROM pelanggaran WHERE id = ?", (pid,))
    flash("Catatan pelanggaran dihapus.", "success")
    return redirect(request.referrer or url_for("kedisiplinan.pelanggaran"))


@bp.route("/jenis", methods=["POST"])
@roles("bk")
@feature("pelanggaran")
def jenis_simpan():
    nama = request.form.get("nama", "").strip()
    if not nama:
        flash("Nama jenis pelanggaran wajib diisi.", "error")
    else:
        vals = (nama, request.form.get("kategori") or None, form_int("poin", 0),
                1 if request.form.get("notif_aktif") else 0)
        jid = form_int("id")
        if jid:
            execute("UPDATE jenis_pelanggaran SET nama = ?, kategori = ?, poin = ?, "
                    "notif_aktif = ? WHERE id = ?", vals + (jid,))
        else:
            execute("INSERT INTO jenis_pelanggaran(nama, kategori, poin, notif_aktif) "
                    "VALUES (?,?,?,?)", vals)
        flash("Jenis pelanggaran disimpan.", "success")
    return redirect(url_for("kedisiplinan.pelanggaran", tab="jenis"))


@bp.route("/jenis/<int:jid>/hapus", methods=["POST"])
@roles("bk")
def jenis_hapus(jid):
    execute("DELETE FROM jenis_pelanggaran WHERE id = ?", (jid,))
    flash("Jenis pelanggaran dihapus.", "success")
    return redirect(url_for("kedisiplinan.pelanggaran", tab="jenis"))


# ================================================================ ATURAN JAM
@bp.route("/aturan-jam", methods=["GET", "POST"])
@roles()
@feature("presensi")
def aturan_jam():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in
             ("nama", "jam_masuk", "batas_telat", "batas_pulang_cepat", "jam_pulang", "jam_tutup")}
        times = [f["jam_masuk"], f["batas_telat"], f["batas_pulang_cepat"], f["jam_pulang"],
                 f["jam_tutup"]]
        if not f["nama"] or not all(valid_time(t) for t in times):
            flash("Nama dan semua jam wajib diisi dengan format HH:MM.", "error")
            return redirect(url_for("kedisiplinan.aturan_jam"))
        if times != sorted(times):
            flash("Urutan jam harus: jam masuk ≤ batas telat ≤ mulai absen pulang ≤ jam pulang "
                  "≤ jam tutup.", "error")
            return redirect(url_for("kedisiplinan.aturan_jam"))
        kelas_id = form_int("kelas_id")
        jenjang = None if kelas_id else (request.form.get("jenjang", "").strip() or None)
        vals = (f["nama"], jenjang, kelas_id, *times)
        aid = form_int("id")
        if aid:
            execute("UPDATE aturan_jam SET nama = ?, jenjang = ?, kelas_id = ?, jam_masuk = ?, "
                    "batas_telat = ?, batas_pulang_cepat = ?, jam_pulang = ?, jam_tutup = ? "
                    "WHERE id = ?", vals + (aid,))
        else:
            execute("INSERT INTO aturan_jam(nama, jenjang, kelas_id, jam_masuk, batas_telat, "
                    "batas_pulang_cepat, jam_pulang, jam_tutup) VALUES (?,?,?,?,?,?,?,?)", vals)
        flash("Aturan jam disimpan.", "success")
        return redirect(url_for("kedisiplinan.aturan_jam"))
    rows = query("SELECT a.*, k.nama AS kelas FROM aturan_jam a LEFT JOIN kelas k ON "
                 "k.id = a.kelas_id ORDER BY a.kelas_id IS NOT NULL, a.jenjang IS NOT NULL, a.id")
    edit = query("SELECT * FROM aturan_jam WHERE id = ?", (arg_int("edit"),), one=True)
    jenjang = [r["jenjang"] for r in query("SELECT DISTINCT jenjang FROM kelas WHERE jenjang "
                                           "IS NOT NULL AND jenjang != '' ORDER BY jenjang")]
    return render_template("kedisiplinan/aturan_jam.html", rows=rows, edit=edit,
                           kelas=kelas_options(), jenjang=jenjang)


@bp.route("/aturan-jam/<int:aid>/hapus", methods=["POST"])
@roles()
def aturan_jam_hapus(aid):
    n = query("SELECT COUNT(*) AS n FROM aturan_jam WHERE kelas_id IS NULL AND "
              "(jenjang IS NULL OR jenjang = '')", one=True)["n"]
    row = query("SELECT * FROM aturan_jam WHERE id = ?", (aid,), one=True)
    if row and row["kelas_id"] is None and not row["jenjang"] and n <= 1:
        flash("Aturan default tidak boleh dihapus (minimal harus ada satu).", "error")
    else:
        execute("DELETE FROM aturan_jam WHERE id = ?", (aid,))
        flash("Aturan jam dihapus.", "success")
    return redirect(url_for("kedisiplinan.aturan_jam"))
