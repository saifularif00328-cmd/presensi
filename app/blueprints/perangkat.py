"""Perangkat tap RFID mandiri (ESP32 + RC522) di gerbang / musala.

Admin mendaftarkan perangkat (menu Sistem → Perangkat RFID) dan mendapat KODE + RAHASIA yang
diisikan ke perangkat. Setiap permintaan perangkat ditandatangani:

    X-Perangkat : kode perangkat
    X-Waktu     : waktu kirim (epoch detik, dari NTP)
    X-Nonce     : acak, sekali pakai
    X-Tanda     : hex HMAC-SHA256(rahasia, "<kode>\\n<waktu>\\n<nonce>\\n<body>")

Server menolak tanda tangan salah, jam perangkat meleset > 5 menit, dan nonce yang dipakai ulang
(anti-replay). Tap yang tertunda (internet putus) dikirim ulang dengan `ts` = jam tap asli.
"""
import hashlib
import hmac
import json
import secrets
import time
import unicodedata
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from .. import utils
from ..auth import roles
from ..db import IntegrityError, execute, get_db, get_setting, query
from ..services import ibadah as ibadah_svc
from ..services.attendance import process_scan
from .common import form_int

bp = Blueprint("perangkat", __name__)

MODES = {"auto": "Otomatis (masuk/pulang)", "masuk": "Masuk saja", "pulang": "Pulang saja",
         "ibadah": "Tap ibadah"}
TOLERANSI_JAM = 300      # detik
MAKS_TERTUNDA = 3 * 86400  # tap offline paling lama 3 hari


# ================================================================ ADMIN
@bp.route("/sistem/perangkat", methods=["GET", "POST"])
@roles()
def daftar():
    if request.method == "POST":
        aksi = request.form.get("aksi", "simpan")
        pid = form_int("id")
        if aksi == "hapus" and pid:
            execute("DELETE FROM perangkat WHERE id = ?", (pid,))
            flash("Perangkat dihapus.", "success")
        elif aksi == "rahasia" and pid:
            execute("UPDATE perangkat SET rahasia = ? WHERE id = ?", (_rahasia(), pid))
            flash("Rahasia baru dibuat. Perbarui juga isian di perangkat.", "success")
            return redirect(url_for("perangkat.daftar", lihat=pid))
        else:
            nama = request.form.get("nama", "").strip()
            mode = request.form.get("mode", "auto")
            if not nama or mode not in MODES:
                flash("Nama dan mode perangkat wajib diisi.", "error")
                return redirect(url_for("perangkat.daftar"))
            vals = (nama, mode, form_int("ibadah_id") if mode == "ibadah" else None,
                    1 if request.form.get("aktif") else 0, form_int("gerbang_id"))
            if pid:
                execute("UPDATE perangkat SET nama = ?, mode = ?, ibadah_id = ?, aktif = ?, "
                        "gerbang_id = ? WHERE id = ?", vals + (pid,))
            else:
                try:
                    pid = execute("INSERT INTO perangkat(nama, mode, ibadah_id, aktif, gerbang_id, "
                                  "kode, rahasia) VALUES (?,?,?,?,?,?,?)",
                                  vals + (_kode(), _rahasia()))
                except IntegrityError:
                    flash("Gagal membuat kode perangkat, coba lagi.", "error")
                    return redirect(url_for("perangkat.daftar"))
            flash("Perangkat disimpan.", "success")
            return redirect(url_for("perangkat.daftar", lihat=pid))
        return redirect(url_for("perangkat.daftar"))
    rows = query("SELECT p.*, i.nama AS ibadah, g.nama AS gerbang FROM perangkat p "
                 "LEFT JOIN ibadah i ON i.id = p.ibadah_id LEFT JOIN gerbang g ON g.id = p.gerbang_id "
                 "ORDER BY p.nama")
    lihat = next((r for r in rows if r["id"] == request.args.get("lihat", type=int)), None)
    edit = next((r for r in rows if r["id"] == request.args.get("edit", type=int)), None)
    now = utils.now()
    for r in rows:
        t = utils.parse_datetime(r["terakhir_aktif"])
        r["online"] = t is not None and (now - t).total_seconds() < 180
    return render_template("sistem/perangkat.html", rows=rows, lihat=lihat, edit=edit, MODES=MODES,
                           ibadah=query("SELECT id, nama FROM ibadah ORDER BY jam_mulai"),
                           gerbang=query("SELECT id, nama FROM gerbang WHERE aktif = 1 "
                                         "ORDER BY urutan, nama"),
                           server=get_setting("alamat_publik") or request.url_root.rstrip("/"))


def _kode():
    return "ESP-" + secrets.token_hex(3).upper()


def _rahasia():
    return secrets.token_urlsafe(24)


# ================================================================ API PERANGKAT
def _epoch_ke_lokal(ts):
    return datetime.fromtimestamp(ts, utils.zona()).replace(tzinfo=None)


def _tolak(kode, pesan, status=401, **extra):
    return jsonify({"ok": False, "error": kode, "pesan": pesan, "baris1": "DITOLAK",
                    "baris2": pesan[:16], "nada": "err", **extra}), status


def verifikasi_tanda(tabel, header_kode="X-Perangkat"):
    """Periksa permintaan bertanda tangan HMAC dari perangkat (`perangkat`) atau Presensiku Pos
    (`pos`). Mengembalikan (baris, body_dict, respons_error)."""
    kode = request.headers.get(header_kode, "")
    waktu = request.headers.get("X-Waktu", "")
    nonce = request.headers.get("X-Nonce", "")
    tanda = request.headers.get("X-Tanda", "")
    body = request.get_data() or b""
    p = query(f"SELECT * FROM {tabel} WHERE kode = ?", (kode,), one=True)
    if p is None or not p["aktif"] or (tabel == "pos" and not p["terpasang"]):
        return None, None, _tolak("perangkat", "Perangkat tidak terdaftar/nonaktif")
    pesan = f"{kode}\n{waktu}\n{nonce}\n".encode() + body
    harap = hmac.new(p["rahasia"].encode(), pesan, hashlib.sha256).hexdigest()
    if not tanda or not hmac.compare_digest(tanda.lower(), harap):
        return None, None, _tolak("tanda", "Rahasia perangkat salah")
    try:
        w = int(waktu)
    except ValueError:
        w = 0
    server = int(time.time())
    if abs(server - w) > TOLERANSI_JAM:
        return None, None, _tolak("waktu", "Jam perangkat salah", server_time=server)
    if not nonce or len(nonce) > 40:
        return None, None, _tolak("nonce", "Nonce tidak valid")
    try:
        execute("INSERT INTO perangkat_nonce(kode, nonce) VALUES (?, ?)", (kode, nonce))
    except IntegrityError:
        return None, None, _tolak("replay", "Permintaan ganda", 409)
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except ValueError:
        data = {}
    execute(f"UPDATE {tabel} SET terakhir_aktif = ?, ip = ?, versi = ? WHERE id = ?",
            (utils.now().strftime("%Y-%m-%d %H:%M:%S"), request.remote_addr,
             (request.headers.get("X-Versi") or "")[:20], p["id"]))
    return p, data, None


def _verifikasi():
    return verifikasi_tanda("perangkat")


def tap_tertunda(data):
    """Jam tap asli (`ts` epoch) untuk tap yang tertunda, None = sekarang."""
    try:
        ts = int(data.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0
    if ts:
        t = _epoch_ke_lokal(ts)
        umur = (utils.now() - t).total_seconds()
        if -60 <= umur <= MAKS_TERTUNDA:
            return t
    return None


def nama_gerbang(gerbang_id):
    if not gerbang_id:
        return None
    g = query("SELECT nama FROM gerbang WHERE id = ?", (gerbang_id,), one=True)
    return g["nama"] if g else None


def _ascii(teks):
    """LCD karakter hanya bisa ASCII: é -> e, dll."""
    return unicodedata.normalize("NFKD", teks or "").encode("ascii", "ignore").decode()


def _lcd(res, mode):
    """Dua baris teks (16 karakter, ASCII) untuk LCD perangkat."""
    b1, b2 = _lcd_mentah(res, mode)
    return _ascii(b1)[:16], _ascii(b2)[:16]


def _lcd_mentah(res, mode):
    siswa = res.get("siswa") or {}
    nama = (siswa.get("nama") or "").upper()[:16]
    if res.get("ok"):
        label = {"masuk": "MASUK", "pulang": "PULANG"}.get(res.get("jenis"), "TAP")
        if mode == "ibadah":
            label = "IBADAH"
        status = {"Telat": "TELAT", "Pulang Cepat": "CEPAT"}.get(res.get("status"), "OK")
        return nama or label, f"{label} {res.get('jam', '')} {status}"[:16]
    return (nama or "GAGAL"), (res.get("pesan") or "")[:16]


@bp.route("/api/perangkat/ping", methods=["POST"])
def api_ping():
    p, _data, err = _verifikasi()
    if err:
        return err
    # bersihkan nonce lama (anti-replay cukup 2 hari)
    execute("DELETE FROM perangkat_nonce WHERE waktu < NOW() - INTERVAL 2 DAY")
    return jsonify({"ok": True, "nama": p["nama"], "mode": p["mode"],
                    "sekolah": get_setting("nama_sekolah"), "server_time": int(time.time()),
                    "baris1": _ascii(get_setting("nama_sekolah"))[:16],
                    "baris2": {"auto": "Mode Masuk/Plg", "masuk": "Mode Masuk",
                               "pulang": "Mode Pulang", "ibadah": "Mode Ibadah"}[p["mode"]]})


@bp.route("/api/perangkat/tap", methods=["POST"])
def api_tap():
    p, data, err = _verifikasi()
    if err:
        return err
    # "uid" = kartu RFID; "kode" = isi QR dari modul scanner QR (GM65/GM861) di ESP32
    uid = str(data.get("uid") or data.get("kode") or "")[:200]
    waktu = tap_tertunda(data)
    db = get_db()
    if p["mode"] == "ibadah":
        ib = None
        if p["ibadah_id"]:
            ib = query("SELECT * FROM ibadah WHERE id = ?", (p["ibadah_id"],), one=True)
        else:
            ib = ibadah_svc.jadwal_sekarang(waktu, db=db)
        res = ibadah_svc.tap(uid, ib, db, waktu=waktu, metode="rfid")
    else:
        from ..qr import jenis_kartu
        res = process_scan(uid, p["mode"], "qr" if jenis_kartu(uid) == "qr" else "rfid", db=db,
                           waktu=waktu, gerbang=nama_gerbang(p["gerbang_id"]) or p["nama"])
    if not res.get("ok") and res.get("pesan") == "Kartu RFID belum terdaftar":
        from ..rfid import candidates, catat_tak_dikenal
        c = candidates(uid)
        if c:
            catat_tak_dikenal(c[0], p["nama"], db=db)
            db.commit()
    b1, b2 = _lcd(res, p["mode"])
    nada = "ok" if res.get("ok") else ("warn" if res.get("level") == "warning" else "err")
    return jsonify({"ok": bool(res.get("ok")), "level": res.get("level"), "pesan": res.get("pesan"),
                    "nama": (res.get("siswa") or {}).get("nama"), "baris1": b1, "baris2": b2,
                    "nada": nada})
