"""Gerbang, Presensiku Pos (aplikasi Windows multi-scanner), dan Layar Gerbang.

Presensiku Pos dipasang di satu PC pos sekolah dan membaca BANYAK scanner sekaligus (scanner
USB mode keyboard dibedakan per alat lewat Windows Raw Input, scanner mode COM, dongle
nirkabel). Pos dipasangkan dengan KODE PASANG sekali pakai dari halaman admin, lalu setiap
permintaan ditandatangani HMAC seperti perangkat ESP32 (lihat perangkat.verifikasi_tanda):

    X-Pos, X-Waktu, X-Nonce, X-Tanda = hex HMAC-SHA256(rahasia, "<kode>\\n<waktu>\\n<nonce>\\n<body>")

API Pos:
    POST /api/pos/pasang   {kode_pasang, nama_pc, versi}            -> kode + rahasia (sekali)
    POST /api/pos/sinkron  {versi, antrean, scanner:[...]}          -> gerbang, scanner, pengaturan
    POST /api/pos/scanner  {kunci, jenis, label, gerbang_id, nama}  -> petakan scanner ke gerbang
    POST /api/pos/siswa    {versi}                                  -> salinan data siswa (offline)
    POST /api/pos/foto     {id}                                     -> foto siswa
    POST /api/pos/scan     {scans:[{uuid, kode, kunci, ts}]}        -> hasil per scan (idempoten)
"""
import hashlib
import json
import os
import secrets
from datetime import timedelta

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)

from .. import config, security, utils
from ..auth import roles
from ..db import IntegrityError, execute, get_db, get_setting, query, set_setting
from ..services.attendance import process_scan
from .common import form_int
from .perangkat import MODES as MODE_PERANGKAT
from .perangkat import tap_tertunda, verifikasi_tanda

bp = Blueprint("pos", __name__)

MODES = {k: v for k, v in MODE_PERANGKAT.items() if k != "ibadah"}
PASANG_MENIT = 30
MAKS_SCAN_PER_KIRIM = 200
ABJAD_PASANG = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # tanpa 0/O/1/I agar tidak tertukar


def _kode_pasang():
    k = "".join(secrets.choice(ABJAD_PASANG) for _ in range(8))
    return f"{k[:4]}-{k[4:]}"


def _sekarang_str(delta=None):
    t = utils.now() + (delta or timedelta())
    return t.strftime("%Y-%m-%d %H:%M:%S")


def _gerbang_aktif():
    return query("SELECT id, nama, mode FROM gerbang WHERE aktif = 1 ORDER BY urutan, nama")


# ================================================================ ADMIN
@bp.route("/sistem/perangkat-scan", methods=["GET", "POST"])
@roles()
def halaman():
    if request.method == "POST":
        aksi = request.form.get("aksi", "")
        gid, pid, sid = form_int("gerbang_id"), form_int("pos_id"), form_int("scanner_id")
        if aksi == "gerbang_simpan":
            nama = request.form.get("nama", "").strip()[:60]
            mode = request.form.get("mode", "auto")
            if not nama or mode not in MODES:
                flash("Nama gerbang wajib diisi.", "error")
            else:
                try:
                    if gid:
                        execute("UPDATE gerbang SET nama = ?, mode = ?, urutan = ?, aktif = ? "
                                "WHERE id = ?", (nama, mode, form_int("urutan", 0),
                                                 1 if request.form.get("aktif") else 0, gid))
                    else:
                        execute("INSERT INTO gerbang(nama, mode, urutan) VALUES (?,?,?)",
                                (nama, mode, form_int("urutan", 0)))
                    flash("Gerbang disimpan.", "success")
                except IntegrityError:
                    flash("Nama gerbang sudah dipakai.", "error")
        elif aksi == "gerbang_hapus" and gid:
            execute("DELETE FROM gerbang WHERE id = ?", (gid,))
            flash("Gerbang dihapus.", "success")
        elif aksi == "pos_tambah":
            nama = request.form.get("nama", "").strip()[:100] or "PC Pos"
            pid = execute("INSERT INTO pos(nama, kode, rahasia, kode_pasang, pasang_sampai) "
                          "VALUES (?,?,?,?,?)",
                          (nama, "POS-" + secrets.token_hex(4).upper(), secrets.token_urlsafe(24),
                           _kode_pasang(), _sekarang_str(timedelta(minutes=PASANG_MENIT))))
            flash("Pos ditambahkan. Masukkan KODE PASANG di aplikasi Presensiku Pos.", "success")
            return redirect(url_for("pos.halaman", pasang=pid))
        elif aksi == "pos_pasang_ulang" and pid:
            # rahasia baru: PC lama otomatis terputus sampai dipasangkan ulang
            execute("UPDATE pos SET rahasia = ?, terpasang = 0, kode_pasang = ?, pasang_sampai = ? "
                    "WHERE id = ?", (secrets.token_urlsafe(24), _kode_pasang(),
                                     _sekarang_str(timedelta(minutes=PASANG_MENIT)), pid))
            flash("Kode pasang baru dibuat. PC lama terputus sampai dipasangkan ulang.", "success")
            return redirect(url_for("pos.halaman", pasang=pid))
        elif aksi == "pos_aktif" and pid:
            execute("UPDATE pos SET aktif = 1 - aktif WHERE id = ?", (pid,))
        elif aksi == "pos_hapus" and pid:
            execute("DELETE FROM pos WHERE id = ?", (pid,))
            flash("Pos dihapus.", "success")
        elif aksi == "scanner_simpan" and sid:
            execute("UPDATE pos_scanner SET nama = ?, gerbang_id = ?, aktif = ? WHERE id = ?",
                    (request.form.get("nama", "").strip()[:60] or None, form_int("gerbang"),
                     1 if request.form.get("aktif") else 0, sid))
            flash("Scanner disimpan.", "success")
        elif aksi == "scanner_hapus" and sid:
            execute("DELETE FROM pos_scanner WHERE id = ?", (sid,))
            flash("Scanner dihapus. Bila di-scan lagi, Pos akan menanyakan gerbangnya.", "success")
        elif aksi == "pengaturan":
            jeda = form_int("scan_jeda_ganda", 60)
            set_setting("scan_jeda_ganda", str(max(0, min(jeda, 3600))))
            flash("Pengaturan disimpan.", "success")
        return redirect(url_for("pos.halaman"))

    pos_rows = query("SELECT * FROM pos ORDER BY nama")
    now = utils.now()
    for p in pos_rows:
        t = utils.parse_datetime(p["terakhir_aktif"])
        p["online"] = t is not None and (now - t).total_seconds() < 180
        sampai = utils.parse_datetime(p["pasang_sampai"])
        p["kode_berlaku"] = bool(p["kode_pasang"]) and sampai is not None and sampai > now
        p["scanner"] = query("SELECT sc.*, g.nama AS gerbang FROM pos_scanner sc LEFT JOIN gerbang g "
                             "ON g.id = sc.gerbang_id WHERE sc.pos_id = ? ORDER BY sc.id",
                             (p["id"],))
    return render_template("sistem/perangkat_scan.html", pos=pos_rows,
                           gerbang=query("SELECT * FROM gerbang ORDER BY urutan, nama"),
                           MODES=MODES, pasang=request.args.get("pasang", type=int),
                           edit_gerbang=request.args.get("edit_gerbang", type=int),
                           jeda=get_setting("scan_jeda_ganda") or "60",
                           server=get_setting("alamat_publik") or request.url_root.rstrip("/"))


# ================================================================ LAYAR GERBANG (server)
@bp.route("/presensi/layar-gerbang")
@roles("piket")
def layar():
    """Layar split per gerbang langsung dari server (ESP32 / scanner per perangkat). Untuk banyak
    scanner di satu PC, layar yang sama disajikan oleh Presensiku Pos secara lokal."""
    return render_template("presensi/layar_gerbang.html",
                           sumber=url_for("pos.api_layar"))


def _level(jenis, status):
    if jenis == "gagal":
        return "error"
    if jenis == "peringatan":
        return "warning"
    return "warning" if status in ("Telat", "Pulang Cepat") else "success"


@bp.route("/presensi/api/layar")
@roles("piket")
def api_layar():
    sejak = request.args.get("sejak", type=int)
    awal = sejak is None
    rows = query("SELECT l.id, l.waktu, l.jenis, l.status, l.pesan, l.gerbang, s.nama, s.foto, "
                 "k.nama AS kelas FROM scan_log l LEFT JOIN siswa s ON s.id = l.siswa_id "
                 "LEFT JOIN kelas k ON k.id = s.kelas_id WHERE date(l.waktu) = ? "
                 "AND l.jenis IN ('masuk', 'pulang', 'peringatan', 'gagal') AND l.id > ? "
                 "ORDER BY l.id DESC LIMIT 60", (utils.today_str(), sejak or 0))
    item = []
    for r in reversed(rows):
        w = utils.parse_datetime(r["waktu"])
        item.append({"id": r["id"], "jam": w.strftime("%H:%M:%S") if w else "",
                     "gerbang": r["gerbang"] or "", "jenis": r["jenis"], "status": r["status"],
                     "level": _level(r["jenis"], r["status"]), "pesan": r["pesan"] or "",
                     "siswa": {"nama": r["nama"], "kelas": r["kelas"] or "",
                               "foto": url_for("uploads", filename=r["foto"]) if r["foto"] else None}
                     if r["nama"] else None, "awal": awal})
    hadir = query("SELECT gerbang_masuk AS g, COUNT(*) AS n FROM presensi WHERE tanggal = ? "
                  "AND jam_masuk IS NOT NULL GROUP BY gerbang_masuk", (utils.today_str(),))
    return jsonify({"sekolah": get_setting("nama_sekolah"),
                    "gerbang": [g["nama"] for g in _gerbang_aktif()],
                    "hadir": {(h["g"] or ""): h["n"] for h in hadir},
                    "item": item, "terakhir": max([sejak or 0] + [i["id"] for i in item]),
                    "online": True, "waktu": utils.now().strftime("%H:%M:%S")})


# ================================================================ API POS
def _tolak(pesan, status=400, **extra):
    return jsonify({"ok": False, "pesan": pesan, **extra}), status


@bp.route("/api/pos/pasang", methods=["POST"])
def api_pasang():
    ip = request.remote_addr or ""
    if security.terkunci("pos-pasang", ip):
        return _tolak("Terlalu banyak kode salah. Coba lagi 15 menit lagi.", 429)
    data = request.get_json(silent=True) or {}
    kode = (data.get("kode_pasang") or "").strip().upper().replace(" ", "")
    if len(kode) == 8:
        kode = f"{kode[:4]}-{kode[4:]}"
    p = query("SELECT * FROM pos WHERE kode_pasang = ? AND aktif = 1", (kode,), one=True) \
        if kode else None
    sampai = utils.parse_datetime(p["pasang_sampai"]) if p else None
    if p is None or sampai is None or sampai < utils.now():
        security.catat_gagal("pos-pasang", ip)
        return _tolak("Kode pasang salah atau kedaluwarsa. Buat kode baru di menu Perangkat Scan.",
                      403)
    execute("UPDATE pos SET terpasang = 1, kode_pasang = NULL, pasang_sampai = NULL, "
            "versi = ?, ip = ?, terakhir_aktif = ? WHERE id = ?",
            (str(data.get("versi") or "")[:20], ip, _sekarang_str(), p["id"]))
    return jsonify({"ok": True, "kode": p["kode"], "rahasia": p["rahasia"], "nama": p["nama"],
                    "sekolah": get_setting("nama_sekolah")})


def _pos():
    return verifikasi_tanda("pos", "X-Pos")


def _konfig(p):
    scanner = query("SELECT sc.kunci, sc.jenis, sc.label, sc.nama, sc.gerbang_id, sc.aktif, "
                    "g.nama AS gerbang FROM pos_scanner sc LEFT JOIN gerbang g "
                    "ON g.id = sc.gerbang_id WHERE sc.pos_id = ?", (p["id"],))
    return {"ok": True, "pos": p["nama"], "sekolah": get_setting("nama_sekolah"),
            "gerbang": [dict(g) for g in _gerbang_aktif()],
            "scanner": [dict(s) for s in scanner],
            "qr_secret": get_setting("qr_secret"),
            "jeda_ganda": int(get_setting("scan_jeda_ganda") or 60),
            "server_time": int(utils.now().timestamp())}


@bp.route("/api/pos/sinkron", methods=["POST"])
def api_sinkron():
    p, data, err = _pos()
    if err:
        return err
    try:
        antrean = max(0, int(data.get("antrean") or 0))
    except (TypeError, ValueError):
        antrean = 0
    execute("UPDATE pos SET antrean = ? WHERE id = ?", (antrean, p["id"]))
    for sc in (data.get("scanner") or [])[:50]:
        kunci = str(sc.get("kunci") or "")[:64]
        if not kunci:
            continue
        execute("INSERT INTO pos_scanner(pos_id, kunci, jenis, label, terakhir) VALUES (?,?,?,?,?) "
                "ON DUPLICATE KEY UPDATE label = VALUES(label), terakhir = VALUES(terakhir)",
                (p["id"], kunci, "com" if sc.get("jenis") == "com" else "keyboard",
                 str(sc.get("label") or "")[:150], _sekarang_str()))
    execute("DELETE FROM pos_scan WHERE waktu < NOW() - INTERVAL 7 DAY")
    execute("DELETE FROM perangkat_nonce WHERE waktu < NOW() - INTERVAL 2 DAY")
    return jsonify(_konfig(p))


@bp.route("/api/pos/scanner", methods=["POST"])
def api_scanner():
    """Pos memetakan scanner baru ke gerbang (dipilih petugas di layar Pos)."""
    p, data, err = _pos()
    if err:
        return err
    kunci = str(data.get("kunci") or "")[:64]
    if not kunci:
        return _tolak("Kunci scanner kosong")
    gid = data.get("gerbang_id")
    if gid is not None and not query("SELECT 1 FROM gerbang WHERE id = ?", (gid,), one=True):
        return _tolak("Gerbang tidak ada")
    execute("INSERT INTO pos_scanner(pos_id, kunci, jenis, label, nama, gerbang_id, aktif, terakhir) "
            "VALUES (?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE jenis = VALUES(jenis), "
            "label = COALESCE(NULLIF(VALUES(label), ''), label), "
            "nama = COALESCE(VALUES(nama), nama), gerbang_id = VALUES(gerbang_id), "
            "aktif = VALUES(aktif), terakhir = VALUES(terakhir)",
            (p["id"], kunci, "com" if data.get("jenis") == "com" else "keyboard",
             str(data.get("label") or "")[:150], str(data.get("nama") or "")[:60] or None, gid,
             0 if data.get("abaikan") else 1, _sekarang_str()))
    return jsonify(_konfig(p))


def _data_siswa():
    rows = query("SELECT s.id, s.nama, s.nis, s.qr_token, s.rfid_uid, s.foto, k.nama AS kelas "
                 "FROM siswa s LEFT JOIN kelas k ON k.id = s.kelas_id WHERE s.aktif = 1 "
                 "ORDER BY s.id")
    siswa = []
    for r in rows:
        d = dict(r)
        f = os.path.join(config.UPLOAD_DIR, r["foto"]) if r["foto"] else None
        d["foto_versi"] = int(os.path.getmtime(f)) if f and os.path.exists(f) else 0
        siswa.append(d)
    blokir = [r["uid"] for r in query("SELECT DISTINCT uid FROM rfid_blokir")]
    versi = hashlib.sha1(json.dumps([siswa, blokir], sort_keys=True, default=str)
                         .encode()).hexdigest()[:16]
    return versi, siswa, blokir


@bp.route("/api/pos/siswa", methods=["POST"])
def api_siswa():
    p, data, err = _pos()
    if err:
        return err
    versi, siswa, blokir = _data_siswa()
    if data.get("versi") == versi:
        return jsonify({"ok": True, "versi": versi, "sama": True})
    return jsonify({"ok": True, "versi": versi, "siswa": siswa, "blokir": blokir})


@bp.route("/api/pos/foto", methods=["POST"])
def api_foto():
    p, data, err = _pos()
    if err:
        return err
    r = query("SELECT foto FROM siswa WHERE id = ? AND aktif = 1", (data.get("id"),), one=True)
    if not r or not r["foto"]:
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, r["foto"])


@bp.route("/api/pos/scan", methods=["POST"])
def api_scan():
    p, data, err = _pos()
    if err:
        return err
    from ..qr import jenis_kartu
    db = get_db()
    hasil = []
    for sc in (data.get("scans") or [])[:MAKS_SCAN_PER_KIRIM]:
        uuid = str(sc.get("uuid") or "")[:40]
        teks = str(sc.get("kode") or "").strip()[:200]
        if not uuid or not teks:
            continue
        lama = query("SELECT hasil FROM pos_scan WHERE uuid = ?", (uuid,), one=True)
        if lama:                                    # kiriman ulang (koneksi putus sebelum balasan)
            hasil.append({**json.loads(lama["hasil"]), "uuid": uuid, "ulang": True})
            continue
        scanner = query("SELECT sc.*, g.nama AS gerbang, g.mode, g.aktif AS gerbang_aktif "
                        "FROM pos_scanner sc LEFT JOIN gerbang g ON g.id = sc.gerbang_id "
                        "WHERE sc.pos_id = ? AND sc.kunci = ?",
                        (p["id"], str(sc.get("kunci") or "")[:64]), one=True)
        if scanner is None or not scanner["aktif"] or not scanner["gerbang_id"]:
            # belum dipetakan ke gerbang (atau diabaikan): tidak disimpan agar bisa dikirim ulang
            # setelah petugas memilih gerbangnya
            hasil.append({"uuid": uuid, "ok": False, "level": "error", "error": "scanner",
                          "pesan": "Scanner belum didaftarkan ke gerbang"})
            continue
        waktu = tap_tertunda(sc)
        if sc.get("ts") and waktu is None:
            res = {"ok": False, "level": "error",
                   "pesan": "Scan tertunda lebih dari 3 hari atau jam PC salah — dibuang"}
        else:
            mode = scanner["mode"] if scanner["mode"] in MODES else "auto"
            gerbang = scanner["gerbang"]
            res = process_scan(teks, mode, "qr" if jenis_kartu(teks) == "qr" else "rfid",
                               db=db, waktu=waktu, gerbang=gerbang)
            res["gerbang"] = gerbang
        execute("INSERT INTO pos_scan(uuid, pos_id, hasil) VALUES (?,?,?)",
                (uuid, p["id"], json.dumps(res, default=str)))
        execute("UPDATE pos_scanner SET terakhir = ? WHERE id = ?", (_sekarang_str(), scanner["id"]))
        hasil.append({**res, "uuid": uuid})
    return jsonify({"ok": True, "hasil": hasil})
