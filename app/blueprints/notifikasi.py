"""Notifikasi WhatsApp: token Fonnte, template pesan, log & kirim ulang."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import utils
from ..auth import feature, roles
from ..db import execute, get_db, get_setting, query, set_setting
from ..services import notify
from .common import arg_int

bp = Blueprint("notifikasi", __name__, url_prefix="/notifikasi")


@bp.route("/pengaturan", methods=["GET", "POST"])
@roles()
@feature("whatsapp")
def pengaturan():
    if request.method == "POST":
        db = get_db()
        token = request.form.get("fonnte_token", "").strip()
        if token:
            # Token disimpan terenkripsi di database lokal
            set_setting("fonnte_token", utils.encrypt(token), db=db, commit=False)
        if request.form.get("hapus_token"):
            set_setting("fonnte_token", "", db=db, commit=False)
        for j in notify.JENIS:
            set_setting(f"wa_on_{j}", "1" if request.form.get(f"wa_on_{j}") else "0", db=db,
                        commit=False)
            tpl = request.form.get(f"wa_tpl_{j}", "").strip()
            if tpl:
                set_setting(f"wa_tpl_{j}", tpl, db=db, commit=False)
        db.commit()
        flash("Pengaturan notifikasi WA disimpan.", "success")
        return redirect(url_for("notifikasi.pengaturan"))
    token = notify.fonnte_token()
    masked = (token[:4] + "•" * 8 + token[-3:]) if len(token) > 8 else ("•" * len(token))
    jenis = [{"key": k, "label": v, "on": get_setting(f"wa_on_{k}") == "1",
              "tpl": get_setting(f"wa_tpl_{k}")} for k, v in notify.JENIS.items()]
    return render_template("notifikasi/pengaturan.html", masked=masked, jenis=jenis,
                           kuota=get_setting("fonnte_kuota"),
                           kuota_cek=get_setting("fonnte_kuota_cek"))


@bp.route("/tes", methods=["POST"])
@roles()
@feature("whatsapp")
def tes():
    nomor = utils.normalize_wa(request.form.get("nomor"))
    if not nomor:
        flash("Nomor WA tidak valid.", "error")
    else:
        execute("INSERT INTO notif_queue(jenis, nomor, pesan) VALUES ('tes', ?, ?)",
                (nomor, f"Tes notifikasi dari {get_setting('nama_sekolah')} — Presensi Siswa "
                        f"Digital ({utils.now():%d-%m-%Y %H:%M})."))
        sent = notify.process_queue(get_db())
        flash("Pesan tes terkirim." if sent else "Pesan tes masuk antrian (belum terkirim — cek "
              "token/koneksi di Log Notifikasi).", "success" if sent else "error")
    return redirect(url_for("notifikasi.pengaturan"))


@bp.route("/kuota", methods=["POST"])
@roles()
@feature("whatsapp")
def kuota():
    info = notify.refresh_quota(get_db())
    flash(f"Kuota Fonnte: {info}" if info else "Gagal cek kuota (offline / token belum diisi).",
          "success" if info else "error")
    return redirect(request.referrer or url_for("notifikasi.pengaturan"))


@bp.route("/log")
@roles()
@feature("whatsapp")
def log():
    status = request.args.get("status", "")
    where, args = "", []
    if status in ("Menunggu Koneksi", "Terkirim", "Gagal"):
        where, args = "WHERE n.status = ?", [status]
    page = max(arg_int("page", 1), 1)
    rows = query("SELECT n.*, s.nama FROM notif_queue n LEFT JOIN siswa s ON s.id = n.siswa_id "
                 f"{where} ORDER BY n.id DESC LIMIT 100 OFFSET ?", args + [(page - 1) * 100])
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM notif_queue "
                                                  "GROUP BY status")}
    return render_template("notifikasi/log.html", rows=rows, status=status, counts=counts,
                           page=page, online=None)


@bp.route("/kirim-ulang", methods=["POST"])
@roles()
@feature("whatsapp")
def kirim_ulang():
    nid = request.form.get("id", type=int)
    if nid:
        execute("UPDATE notif_queue SET status = 'Menunggu Koneksi', percobaan = 0, error = NULL "
                "WHERE id = ?", (nid,))
    else:
        execute("UPDATE notif_queue SET status = 'Menunggu Koneksi', percobaan = 0, error = NULL "
                "WHERE status = 'Gagal'")
    sent = notify.process_queue(get_db())
    flash(f"Diproses ulang: {sent} pesan terkirim, sisanya menunggu koneksi.", "success")
    return redirect(url_for("notifikasi.log"))


@bp.route("/proses", methods=["POST"])
@roles()
@feature("whatsapp")
def proses():
    online = notify.is_online()
    sent = notify.process_queue(get_db())
    flash(f"Koneksi internet: {'ONLINE' if online else 'OFFLINE'}. {sent} pesan terkirim.",
          "success" if online else "error")
    return redirect(url_for("notifikasi.log"))
