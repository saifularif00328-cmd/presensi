"""Presensi: Scan QR, Monitor Live, Presensi Manual, Rekap, SMT (semester)."""
from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template, request,
                   url_for)

from .. import utils
from ..auth import feature, roles
from ..db import get_db, get_setting, query
from ..services import webcam
from ..services.attendance import aturan_for, close_day, process_scan, set_manual
from ..services.rekap import rekap_semester
from .common import (arg_date, arg_int, kelas_options, semester_aktif, send_export,
                     valid_time)

bp = Blueprint("presensi", __name__, url_prefix="/presensi")


# ================================================================ SCAN
@bp.route("/scan")
@roles("piket")
@feature("presensi")
def scan():
    tgl = utils.today()
    libur = None if utils.is_school_day(tgl) else (utils.libur_on(tgl) or "Bukan hari sekolah")
    return render_template("presensi/scan.html", aturan=aturan_for(None), libur=libur,
                           webcam=webcam.status())


@bp.route("/api/scan", methods=["POST"])
@roles("piket")
@feature("presensi")
def api_scan():
    data = request.get_json(silent=True) or request.form
    res = process_scan(data.get("code", ""), data.get("mode", "auto"),
                       data.get("metode", "scanner"))
    return jsonify(res)


@bp.route("/webcam", methods=["POST"])
@roles("piket")
def webcam_ctl():
    if request.form.get("aksi") == "stop":
        webcam.stop()
        flash("Scanner webcam server dihentikan.", "success")
    else:
        idx = request.form.get("kamera", "0")
        ok = webcam.start(current_app._get_current_object(),
                          int(idx) if idx.isdigit() else 0, request.form.get("mode", "auto"))
        flash("Scanner webcam server berjalan." if ok else
              f"Tidak dapat memulai webcam: {webcam.status()['error']}", "success" if ok else "error")
    return redirect(url_for("presensi.scan"))


# ================================================================ MONITOR
@bp.route("/monitor")
@roles("piket", "bk")
@feature("presensi")
def monitor():
    return render_template("presensi/monitor.html", kelas=kelas_options(),
                           kelas_id=arg_int("kelas_id"),
                           refresh=int(get_setting("monitor_refresh_detik") or 3))


@bp.route("/api/monitor")
@roles("piket", "bk")
def api_monitor():
    kelas_id = arg_int("kelas_id")
    tgl = utils.today_str()
    kf, args = "", [tgl]
    if kelas_id:
        kf = " AND s.kelas_id = ?"
        args.append(kelas_id)
    feed = query("SELECT l.id, l.waktu, l.jenis, l.status, l.pesan, l.metode, s.id AS siswa_id, "
                 "s.nama, s.foto, k.nama AS kelas FROM scan_log l "
                 "LEFT JOIN siswa s ON s.id = l.siswa_id LEFT JOIN kelas k ON k.id = s.kelas_id "
                 f"WHERE date(l.waktu) = ? {kf} "
                 "ORDER BY l.id DESC LIMIT 40", args)
    siswa = query("SELECT s.id, s.nama, s.foto, k.nama AS kelas, p.keterangan, p.jam_masuk, "
                  "p.status_masuk, p.jam_pulang, p.status_pulang FROM siswa s "
                  "LEFT JOIN kelas k ON k.id = s.kelas_id LEFT JOIN presensi p "
                  "ON p.siswa_id = s.id AND p.tanggal = ? WHERE s.aktif = 1"
                  f"{kf} ORDER BY k.nama, s.nama", args)
    stats = {"total": len(siswa), "masuk": 0, "telat": 0, "pulang": 0, "izin": 0, "alpha": 0,
             "belum": 0}
    belum, sudah = [], []
    for s in siswa:
        if s["jam_masuk"]:
            stats["masuk"] += 1
            stats["telat"] += s["status_masuk"] == "Telat"
            stats["pulang"] += bool(s["jam_pulang"])
            sudah.append(dict(s))
        elif s["keterangan"] in ("I", "S", "D"):
            stats["izin"] += 1
            sudah.append(dict(s))
        elif s["keterangan"] == "A":
            stats["alpha"] += 1
            belum.append(dict(s))
        else:
            stats["belum"] += 1
            belum.append(dict(s))
    return jsonify({"feed": [dict(r) for r in feed], "stats": stats, "belum": belum,
                    "sudah": sudah, "waktu": utils.now().strftime("%H:%M:%S"),
                    "libur": not utils.is_school_day(utils.today())})


# ================================================================ MANUAL
@bp.route("/manual", methods=["GET", "POST"])
@roles("piket")
@feature("presensi")
def manual():
    kelas_id = arg_int("kelas_id") or (request.form.get("kelas_id", type=int))
    tgl = arg_date("tanggal") or utils.parse_date(request.form.get("tanggal")) or utils.today()
    if tgl > utils.today():
        flash("Tidak bisa mengisi presensi untuk tanggal yang akan datang.", "error")
        tgl = utils.today()
    if request.method == "POST":
        db = get_db()
        n = 0
        for key in request.form:
            if not key.startswith("ket_"):
                continue
            sid = int(key[4:])
            ket = request.form.get(key)
            if ket not in utils.KETERANGAN:
                continue
            jm = request.form.get(f"masuk_{sid}") or None
            jp = request.form.get(f"pulang_{sid}") or None
            if (jm and not valid_time(jm)) or (jp and not valid_time(jp)):
                flash("Format jam harus HH:MM.", "error")
                continue
            if ket == "H" and not jm:
                jm = utils.now().strftime("%H:%M") if tgl == utils.today() else "07:00"
            orig = request.form.get(f"orig_{sid}", "")
            new_sig = f"{ket}|{(jm or '')[:5]}|{(jp or '')[:5]}|{request.form.get(f'cat_{sid}', '')}"
            if orig == new_sig:
                continue  # tidak berubah
            set_manual(db, sid, tgl.isoformat(), ket, jm, jp,
                       request.form.get(f"cat_{sid}") or None)
            n += 1
        flash(f"{n} data presensi disimpan." if n else "Tidak ada perubahan.", "success")
        return redirect(url_for("presensi.manual", kelas_id=kelas_id, tanggal=tgl.isoformat()))
    rows = []
    if kelas_id:
        rows = query("SELECT s.id, s.nis, s.nama, p.keterangan, p.jam_masuk, p.jam_pulang, "
                     "p.status_masuk, p.status_pulang, p.catatan, p.sumber FROM siswa s "
                     "LEFT JOIN presensi p ON p.siswa_id = s.id AND p.tanggal = ? "
                     "WHERE s.kelas_id = ? AND s.aktif = 1 ORDER BY s.nama",
                     (tgl.isoformat(), kelas_id))
    libur = None if utils.is_school_day(tgl) else (utils.libur_on(tgl) or "Bukan hari sekolah")
    return render_template("presensi/manual.html", kelas=kelas_options(), kelas_id=kelas_id,
                           tgl=tgl, rows=rows, libur=libur)


@bp.route("/tutup-hari", methods=["POST"])
@roles()
def tutup_hari():
    n = close_day(get_db(), utils.today(), force=True)
    flash(f"Tutup harian diproses: {n} siswa ditandai Alpha, yang belum absen pulang "
          "ditandai 'Belum Pulang'.", "success")
    return redirect(request.referrer or url_for("presensi.monitor"))


# ================================================================ REKAP
@bp.route("/rekap")
@roles("piket", "bk")
@feature("rekap")
def rekap():
    dari = arg_date("dari", utils.today())
    sampai = arg_date("sampai", dari)
    if sampai < dari:
        dari, sampai = sampai, dari
    kelas_id = arg_int("kelas_id")
    ket = request.args.get("ket", "")
    where, args = ["p.tanggal BETWEEN ? AND ?"], [dari.isoformat(), sampai.isoformat()]
    if kelas_id:
        where.append("p.kelas_id = ?")
        args.append(kelas_id)
    if ket in utils.KETERANGAN:
        where.append("p.keterangan = ?")
        args.append(ket)
    elif ket == "T":
        where.append("p.status_masuk = 'Telat'")
    rows = query("SELECT p.*, s.nama, s.nis, k.nama AS kelas FROM presensi p "
                 "JOIN siswa s ON s.id = p.siswa_id LEFT JOIN kelas k ON k.id = p.kelas_id "
                 f"WHERE {' AND '.join(where)} ORDER BY p.tanggal DESC, k.nama, s.nama", args)
    fmt = request.args.get("format")
    if fmt in ("xlsx", "pdf"):
        data = [(r["tanggal"], r["nis"] or "", r["nama"], r["kelas"] or "", r["keterangan"],
                 (r["jam_masuk"] or "")[:5], r["status_masuk"] or "", (r["jam_pulang"] or "")[:5],
                 r["status_pulang"] or "", r["sumber"], r["catatan"] or "") for r in rows]
        return send_export(fmt, f"rekap-presensi-{dari}-{sampai}", "Rekap Presensi",
                           ["Tanggal", "NIS", "Nama", "Kelas", "Ket", "Masuk", "Status Masuk",
                            "Pulang", "Status Pulang", "Sumber", "Catatan"], data,
                           f"{get_setting('nama_sekolah')} — {dari} s.d. {sampai}")
    ringkas = {k: sum(1 for r in rows if r["keterangan"] == k) for k in utils.KETERANGAN}
    ringkas["T"] = sum(1 for r in rows if r["status_masuk"] == "Telat")
    return render_template("presensi/rekap.html", rows=rows, dari=dari, sampai=sampai,
                           kelas=kelas_options(), kelas_id=kelas_id, ket=ket, ringkas=ringkas)


@bp.route("/smt")
@roles("piket", "bk")
@feature("rekap")
def smt():
    periode = query("SELECT * FROM tahun_ajaran ORDER BY tanggal_mulai DESC")
    pid = arg_int("periode")
    p = next((x for x in periode if x["id"] == pid), None) or semester_aktif() or \
        (periode[0] if periode else None)
    kelas_id = arg_int("kelas_id")
    rows, efektif = [], 0
    if p:
        rows, efektif = rekap_semester(get_db(), utils.parse_date(p["tanggal_mulai"]),
                                       utils.parse_date(p["tanggal_selesai"]), kelas_id)
    fmt = request.args.get("format")
    if fmt in ("xlsx", "pdf") and p:
        data = [(i, r["nis"] or "", r["nama"], r["kelas"] or "", r["H"], r["telat"], r["I"],
                 r["S"], r["A"], r["D"], r["efektif"], f"{r['persen']}%")
                for i, r in enumerate(rows, 1)]
        return send_export(fmt, f"smt-presensi-{p['nama'].replace('/', '-')}-{p['semester']}",
                           f"Rekap Presensi Semester {p['semester']} {p['nama']}",
                           ["No", "NIS", "Nama", "Kelas", "H", "Telat", "I", "S", "A", "D",
                            "Hari Efektif", "% Hadir"], data,
                           f"{get_setting('nama_sekolah')} — {p['tanggal_mulai']} s.d. "
                           f"{p['tanggal_selesai']}")
    return render_template("presensi/smt.html", periode=periode, p=p, rows=rows,
                           efektif=efektif, kelas=kelas_options(), kelas_id=kelas_id)
