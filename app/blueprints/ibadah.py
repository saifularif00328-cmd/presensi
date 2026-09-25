"""Modul Ibadah (opsional, tier Enterprise): Daftar, Tap, Rekap, SMT."""
from functools import wraps

from flask import (Blueprint, flash, jsonify, redirect, render_template, request,
                   url_for)

from .. import utils
from ..auth import feature, roles
from ..db import execute, get_db, get_setting, query
from ..qr import find_siswa
from ..services.attendance import _log
from .common import arg_date, arg_int, form_int, kelas_options, semester_aktif, send_export, \
    valid_time

bp = Blueprint("ibadah", __name__, url_prefix="/ibadah")


def modul_aktif(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if get_setting("modul_ibadah_aktif") != "1":
            flash("Modul Ibadah sedang dinonaktifkan. Aktifkan di menu Pengaturan.", "error")
            return redirect(url_for("main.beranda"))
        return view(*a, **kw)
    return wrapped


def _berlaku_hari_ini(ib, d):
    return str(d.isoweekday()) in (ib["hari"] or "").split(",")


# ================================================================ DAFTAR
@bp.route("/daftar", methods=["GET", "POST"])
@roles()
@feature("ibadah")
@modul_aktif
def daftar():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        jm, js = request.form.get("jam_mulai"), request.form.get("jam_selesai")
        hari = ",".join(request.form.getlist("hari"))
        if not nama or not valid_time(jm) or not valid_time(js) or not hari:
            flash("Nama, jam, dan minimal satu hari wajib diisi.", "error")
            return redirect(url_for("ibadah.daftar"))
        vals = (nama, jm, js, hari, request.form.get("jk") or None,
                1 if request.form.get("aktif") else 0)
        iid = form_int("id")
        if iid:
            execute("UPDATE ibadah SET nama = ?, jam_mulai = ?, jam_selesai = ?, hari = ?, "
                    "jk = ?, aktif = ? WHERE id = ?", vals + (iid,))
        else:
            execute("INSERT INTO ibadah(nama, jam_mulai, jam_selesai, hari, jk, aktif) "
                    "VALUES (?,?,?,?,?,?)", vals)
        flash("Jadwal ibadah disimpan.", "success")
        return redirect(url_for("ibadah.daftar"))
    rows = query("SELECT * FROM ibadah ORDER BY jam_mulai")
    edit = query("SELECT * FROM ibadah WHERE id = ?", (arg_int("edit"),), one=True)
    return render_template("ibadah/daftar.html", rows=rows, edit=edit, HARI=utils.HARI)


@bp.route("/daftar/<int:iid>/hapus", methods=["POST"])
@roles()
def hapus(iid):
    execute("DELETE FROM ibadah WHERE id = ?", (iid,))
    flash("Jadwal ibadah dihapus.", "success")
    return redirect(url_for("ibadah.daftar"))


# ================================================================ TAP
@bp.route("/tap")
@roles("piket", "bk")
@feature("ibadah")
@modul_aktif
def tap():
    today = utils.today()
    jadwal = [r for r in query("SELECT * FROM ibadah WHERE aktif = 1 ORDER BY jam_mulai")
              if _berlaku_hari_ini(r, today)]
    now = utils.now().strftime("%H:%M")
    default = next((j["id"] for j in jadwal if j["jam_mulai"] <= now <= j["jam_selesai"]),
                   jadwal[0]["id"] if jadwal else None)
    # Bila tidak ada yang berlaku, jelaskan alasan tiap jadwal agar admin tahu apa yang diubah
    lain = []
    if not jadwal:
        for r in query("SELECT * FROM ibadah ORDER BY jam_mulai"):
            hari = [utils.HARI[int(h) - 1] for h in (r["hari"] or "").split(",") if h]
            alasan = ("Nonaktif" if not r["aktif"] else
                      f"Hanya hari {', '.join(hari) or '-'}; hari ini {utils.HARI[today.weekday()]}")
            lain.append({"id": r["id"], "nama": r["nama"], "alasan": alasan})
    return render_template("ibadah/tap.html", jadwal=jadwal, lain=lain,
                           ibadah_id=arg_int("ibadah_id", default))


@bp.route("/api/tap", methods=["POST"])
@roles("piket", "bk")
@feature("ibadah")
def api_tap():
    data = request.get_json(silent=True) or request.form
    db = get_db()
    ib = query("SELECT * FROM ibadah WHERE id = ?", (int(data.get("ibadah_id") or 0),), one=True)
    if ib is None:
        return jsonify({"ok": False, "level": "error", "pesan": "Pilih jadwal ibadah dahulu"})
    siswa, err = find_siswa(data.get("code", ""))
    if siswa is None:
        return jsonify({"ok": False, "level": "error", "pesan": err})
    info = {"siswa": {"id": siswa["id"], "nama": siswa["nama"], "kelas": siswa["kelas_nama"],
                      "foto": siswa["foto"]}}
    if ib["jk"] and siswa["jk"] and ib["jk"] != siswa["jk"]:
        return jsonify({**info, "ok": False, "level": "warning",
                        "pesan": f"{ib['nama']} tidak berlaku untuk siswa ini"})
    tgl, jam = utils.today_str(), utils.now().strftime("%H:%M:%S")
    ada = query("SELECT jam FROM presensi_ibadah WHERE siswa_id = ? AND ibadah_id = ? AND "
                "tanggal = ?", (siswa["id"], ib["id"], tgl), one=True)
    if ada:
        return jsonify({**info, "ok": False, "level": "warning",
                        "pesan": f"Sudah tap {ib['nama']} pukul {ada['jam'][:5]}"})
    execute("INSERT INTO presensi_ibadah(siswa_id, ibadah_id, tanggal, jam) VALUES (?,?,?,?)",
            (siswa["id"], ib["id"], tgl, jam), db=db, commit=False)
    _log(db, siswa["id"], "ibadah", ib["nama"], f"Tap {ib['nama']} berhasil", "kamera")
    db.commit()
    return jsonify({**info, "ok": True, "level": "success", "jam": jam[:5],
                    "pesan": f"Tap {ib['nama']} berhasil"})


# ================================================================ REKAP
@bp.route("/rekap")
@roles("piket", "bk")
@feature("ibadah")
@modul_aktif
def rekap():
    tgl = arg_date("tanggal", utils.today())
    kelas_id = arg_int("kelas_id")
    jadwal = [r for r in query("SELECT * FROM ibadah WHERE aktif = 1 ORDER BY jam_mulai")
              if _berlaku_hari_ini(r, tgl)]
    kf, args = "", []
    if kelas_id:
        kf, args = " AND s.kelas_id = ?", [kelas_id]
    siswa = query("SELECT s.id, s.nis, s.nama, s.jk, k.nama AS kelas FROM siswa s LEFT JOIN kelas k "
                  f"ON k.id = s.kelas_id WHERE s.aktif = 1{kf} ORDER BY k.nama, s.nama", args)
    hadir = {}
    for r in query("SELECT siswa_id, ibadah_id, jam FROM presensi_ibadah WHERE tanggal = ?",
                   (tgl.isoformat(),)):
        hadir[(r["siswa_id"], r["ibadah_id"])] = r["jam"][:5]
    fmt = request.args.get("format")
    if fmt in ("xlsx", "pdf"):
        data = [[s["nis"] or "", s["nama"], s["kelas"] or ""] +
                [hadir.get((s["id"], j["id"]), "-") for j in jadwal] for s in siswa]
        return send_export(fmt, f"rekap-ibadah-{tgl}", "Rekap Ibadah Harian",
                           ["NIS", "Nama", "Kelas"] + [j["nama"] for j in jadwal], data,
                           utils.tanggal_indo(tgl))
    ids = {s["id"] for s in siswa}
    jumlah = {}
    for (sid, iid) in hadir:
        if sid in ids:
            jumlah[iid] = jumlah.get(iid, 0) + 1
    return render_template("ibadah/rekap.html", tgl=tgl, jadwal=jadwal, siswa=siswa, hadir=hadir,
                           jumlah=jumlah, kelas=kelas_options(), kelas_id=kelas_id)


@bp.route("/smt")
@roles("piket", "bk")
@feature("ibadah")
@modul_aktif
def smt():
    periode = query("SELECT * FROM tahun_ajaran ORDER BY tanggal_mulai DESC")
    pid = arg_int("periode")
    p = next((x for x in periode if x["id"] == pid), None) or semester_aktif() or \
        (periode[0] if periode else None)
    kelas_id = arg_int("kelas_id")
    jadwal = query("SELECT * FROM ibadah WHERE aktif = 1 ORDER BY jam_mulai")
    rows = []
    if p:
        start = utils.parse_date(p["tanggal_mulai"])
        end = min(utils.parse_date(p["tanggal_selesai"]), utils.today())
        days = utils.school_days(start, end) if end >= start else []
        # jumlah jadwal wajib per jk dalam rentang
        wajib = {"L": 0, "P": 0}
        for d in days:
            for j in jadwal:
                if _berlaku_hari_ini(j, d):
                    for jk in ("L", "P"):
                        if not j["jk"] or j["jk"] == jk:
                            wajib[jk] += 1
        kf, args = "", [start.isoformat(), end.isoformat()]
        if kelas_id:
            kf = " AND s.kelas_id = ?"
            args.append(kelas_id)
        for r in query("SELECT s.id, s.nis, s.nama, s.jk, k.nama AS kelas, COUNT(pi.id) AS hadir "
                       "FROM siswa s LEFT JOIN kelas k ON k.id = s.kelas_id LEFT JOIN "
                       "presensi_ibadah pi ON pi.siswa_id = s.id AND pi.tanggal BETWEEN ? AND ? "
                       f"WHERE s.aktif = 1{kf} GROUP BY s.id ORDER BY k.nama, s.nama", args):
            w = wajib.get(r["jk"] or "L", 0) if r["jk"] else max(wajib.values())
            rows.append({**dict(r), "wajib": w,
                         "persen": round(r["hadir"] * 100 / w, 1) if w else 0})
    fmt = request.args.get("format")
    if fmt in ("xlsx", "pdf") and p:
        data = [(i, r["nis"] or "", r["nama"], r["kelas"] or "", r["hadir"], r["wajib"],
                 f"{r['persen']}%") for i, r in enumerate(rows, 1)]
        return send_export(fmt, f"smt-ibadah-{p['nama'].replace('/', '-')}-{p['semester']}",
                           f"Rekap Ibadah Semester {p['semester']} {p['nama']}",
                           ["No", "NIS", "Nama", "Kelas", "Hadir", "Wajib", "%"], data)
    return render_template("ibadah/smt.html", periode=periode, p=p, rows=rows,
                           kelas=kelas_options(), kelas_id=kelas_id)
