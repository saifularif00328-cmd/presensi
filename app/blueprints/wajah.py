"""Data wajah siswa untuk absen HP: persetujuan orang tua, pendaftaran dari foto / kamera, hapus."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import roles
from ..db import get_setting, query
from ..services import wajah as svc
from .common import arg_int, form_int, kelas_options

bp = Blueprint("wajah", __name__)


def _ids():
    return [int(x) for x in request.form.getlist("siswa_id") if x.isdigit()]


def _siswa_kelas(kelas_id):
    return query("SELECT s.id, s.nama, s.nis, s.foto, w.setuju, w.setuju_oleh, w.setuju_waktu, w.status, "
                 "w.sumber, w.kualitas, w.diperbarui FROM siswa s LEFT JOIN wajah_siswa w ON w.siswa_id = s.id "
                 "WHERE s.aktif = 1 AND s.kelas_id = ? ORDER BY s.nama", (kelas_id,))


@bp.route("/sistem/data-wajah", methods=["GET", "POST"])
@roles()
def halaman():
    kelas_id = form_int("kelas_id") if request.method == "POST" else arg_int("kelas_id")
    if request.method == "POST":
        aksi = request.form.get("aksi")
        oleh = f"{g.user['nama']} (formulir kertas)"
        try:
            if aksi == "setuju":
                for sid in _ids():
                    svc.catat_persetujuan(sid, True, oleh)
                flash(f"Persetujuan {len(_ids())} siswa dicatat.", "success")
            elif aksi == "cabut" and form_int("siswa_id"):
                svc.catat_persetujuan(form_int("siswa_id"), False, g.user["nama"])
                flash("Persetujuan dicabut dan data wajah dihapus.", "success")
            elif aksi == "hapus" and form_int("siswa_id"):
                svc.hapus(form_int("siswa_id"))
                flash("Data wajah dihapus.", "success")
            elif aksi == "daftar_foto":
                ids = _ids() or [r["id"] for r in _siswa_kelas(kelas_id) if r["setuju"] and r["status"] != "siap"]
                ok, gagal = 0, []
                for sid in ids:
                    berhasil, pesan = svc.daftarkan_dari_foto(sid)
                    ok += berhasil
                    if not berhasil:
                        nama = query("SELECT nama FROM siswa WHERE id = ?", (sid,), one=True)
                        gagal.append(f"{nama['nama'] if nama else sid}: {pesan}")
                flash(f"{ok} data wajah dibuat dari foto siswa." if ok else "Tidak ada data wajah baru.",
                      "success" if ok else "info")
                if gagal:
                    flash("Perlu foto ulang — " + "; ".join(gagal[:15]) + (" …" if len(gagal) > 15 else ""), "error")
            elif aksi == "rekam" and form_int("siswa_id"):
                f = request.files.get("foto")
                berhasil, pesan = svc.daftarkan(form_int("siswa_id"), f.read() if f else b"", "kamera")
                flash(pesan if berhasil else f"Gagal: {pesan}. Ulangi dengan wajah lurus & terang.",
                      "success" if berhasil else "error")
        except svc.TidakTersedia as e:
            flash(f"Mesin wajah belum siap: {e}", "error")
        return redirect(url_for("wajah.halaman", kelas_id=kelas_id))
    kelas = kelas_options()
    if kelas_id is None and kelas:
        kelas_id = kelas[0]["id"]
    rows = _siswa_kelas(kelas_id) if kelas_id else []
    hitung = query("SELECT SUM(setuju = 1) AS setuju, SUM(status = 'siap' AND setuju = 1) AS siap, "
                   "SUM(status = 'ulang') AS ulang FROM wajah_siswa w JOIN siswa s ON s.id = w.siswa_id "
                   "WHERE s.aktif = 1", one=True)
    mesin_ok, mesin_ket = svc.status_mesin()
    return render_template("sistem/data_wajah.html", kelas=kelas, kelas_id=kelas_id, rows=rows,
                           hitung={k: hitung[k] or 0 for k in ("setuju", "siap", "ulang")},
                           total=query("SELECT COUNT(*) AS n FROM siswa WHERE aktif = 1", one=True)["n"],
                           mesin_ok=mesin_ok, mesin_ket=mesin_ket, mode=get_setting("hp_wajah") or "mati")


@bp.route("/sistem/data-wajah/formulir")
@roles()
def formulir():
    kelas_id = arg_int("kelas_id")
    k = query("SELECT * FROM kelas WHERE id = ?", (kelas_id,), one=True) if kelas_id else None
    rows = _siswa_kelas(kelas_id) if k else []
    return render_template("sistem/formulir_wajah.html", kelas=k, rows=rows,
                           sekolah=get_setting("nama_sekolah") or "")
