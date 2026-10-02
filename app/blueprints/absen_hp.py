"""Metode absen sekolah (RFID / QR / HP), lokasi absen HP, dan log absen HP untuk ditinjau."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import utils
from ..auth import roles
from ..db import execute, get_setting, query, set_setting
from ..services import absen_hp as svc
from .common import arg_date, form_int, kelas_options

bp = Blueprint("absen_hp", __name__)


def _float(nama):
    try:
        return float(request.form.get(nama, "").replace(",", "."))
    except ValueError:
        return None


def _ids_form(nama):
    return ",".join(str(int(x)) for x in request.form.getlist(nama) if x.isdigit()) or None


def _siswa_dari_nis(teks):
    """'1001, 1002' -> '12,40' (id siswa). NIS tak dikenal dilaporkan."""
    nis = [x for x in teks.replace(";", ",").replace("\n", ",").replace(" ", ",").split(",") if x]
    if not nis:
        return None
    rows = query(f"SELECT id, nis FROM siswa WHERE aktif = 1 AND nis IN ({','.join('?' for _ in nis)})", nis)
    hilang = set(nis) - {r["nis"] for r in rows}
    if hilang:
        flash(f"NIS tidak ditemukan: {', '.join(sorted(hilang))}", "error")
    return ",".join(str(r["id"]) for r in rows) or None


def _nis_dari_ids(ids):
    daftar = [x for x in (ids or "").split(",") if x.isdigit()]
    if not daftar:
        return ""
    rows = query(f"SELECT nis FROM siswa WHERE id IN ({','.join('?' for _ in daftar)})", daftar)
    return ", ".join(r["nis"] for r in rows if r["nis"])


@bp.route("/sistem/metode-absen", methods=["GET", "POST"])
@roles()
def metode():
    if request.method == "POST":
        aksi = request.form.get("aksi")
        if aksi == "metode":
            for m in ("rfid", "qr", "hp"):
                set_setting(f"metode_{m}", "1" if request.form.get(f"metode_{m}") else "0")
            if not any(request.form.get(f"metode_{m}") for m in ("rfid", "qr", "hp")):
                set_setting("metode_qr", "1")
                flash("Minimal satu metode harus aktif — scan QR tetap dinyalakan.", "error")
            cak = request.form.get("hp_cakupan")
            set_setting("hp_cakupan", cak if cak in ("semua", "kelas") else "semua")
            set_setting("hp_kelas", _ids_form("hp_kelas") or "")
            set_setting("hp_akurasi_maks", str(max(10, min(form_int("hp_akurasi_maks", 100), 1000))))
            set_setting("hp_foto_hari", str(max(1, min(form_int("hp_foto_hari", 30), 365))))
            mode = request.form.get("hp_wajah")
            set_setting("hp_wajah", mode if mode in ("mati", "tandai", "wajib") else "mati")
            ambang = _float("wajah_ambang")
            set_setting("wajah_ambang", f"{max(0.30, min(ambang if ambang is not None else 0.42, 0.70)):.2f}")
            set_setting("wajah_tantangan", "1" if request.form.get("wajah_tantangan") else "0")
            flash("Metode absen disimpan.", "success")
        elif aksi == "lokasi":
            lid = form_int("id")
            lat, lng = _float("lat"), _float("lng")
            nama = request.form.get("nama", "").strip()[:100]
            jenis = request.form.get("jenis") if request.form.get("jenis") in ("sekolah", "kegiatan") else "sekolah"
            radius = max(20, min(form_int("radius", 100), 5000))
            if not nama or lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                flash("Isi nama dan koordinat yang benar (klik peta atau 'Pakai lokasi saya').", "error")
                return redirect(url_for("absen_hp.metode", edit=lid) + "#lokasi")
            mulai = utils.parse_date(request.form.get("mulai")) if jenis == "kegiatan" else None
            selesai = utils.parse_date(request.form.get("selesai")) if jenis == "kegiatan" else None
            vals = (nama, jenis, lat, lng, radius, mulai.isoformat() if mulai else None,
                    selesai.isoformat() if selesai else None,
                    _ids_form("kelas_ids") if jenis == "kegiatan" else None,
                    _siswa_dari_nis(request.form.get("siswa_nis", "")) if jenis == "kegiatan" else None,
                    1 if request.form.get("aktif", "1") else 0)
            if lid:
                execute("UPDATE lokasi_absen SET nama=?, jenis=?, lat=?, lng=?, radius=?, mulai=?, "
                        "selesai=?, kelas_ids=?, siswa_ids=?, aktif=? WHERE id = ?", vals + (lid,))
            else:
                execute("INSERT INTO lokasi_absen(nama, jenis, lat, lng, radius, mulai, selesai, "
                        "kelas_ids, siswa_ids, aktif) VALUES (?,?,?,?,?,?,?,?,?,?)", vals)
            flash("Lokasi disimpan.", "success")
        elif aksi == "lokasi_hapus" and form_int("id"):
            execute("DELETE FROM lokasi_absen WHERE id = ?", (form_int("id"),))
            flash("Lokasi dihapus.", "success")
        elif aksi == "reset_hp" and form_int("siswa_id"):
            execute("DELETE FROM hp_siswa WHERE siswa_id = ?", (form_int("siswa_id"),))
            flash("HP siswa direset. Siswa bisa absen dari HP barunya.", "success")
        return redirect(url_for("absen_hp.metode"))
    lokasi = query("SELECT * FROM lokasi_absen ORDER BY jenis DESC, nama")
    edit = next((r for r in lokasi if r["id"] == request.args.get("edit", type=int)), None)
    for r in lokasi:
        r["siswa_nis"] = _nis_dari_ids(r["siswa_ids"])
        r["kelas_set"] = {int(x) for x in (r["kelas_ids"] or "").split(",") if x.isdigit()}
    hp = query("SELECT h.*, s.nama, s.nis, k.nama AS kelas FROM hp_siswa h JOIN siswa s ON s.id = h.siswa_id "
               "LEFT JOIN kelas k ON k.id = s.kelas_id ORDER BY k.nama, s.nama")
    return render_template("sistem/metode_absen.html", lokasi=lokasi, edit=edit, hp=hp,
                           kelas=kelas_options(),
                           hp_kelas={int(x) for x in (get_setting("hp_kelas") or "").split(",") if x.isdigit()},
                           s={k: get_setting(k) for k in ("metode_rfid", "metode_qr", "metode_hp", "hp_cakupan",
                                                          "hp_akurasi_maks", "hp_foto_hari", "hp_wajah",
                                                          "wajah_ambang", "wajah_tantangan")})


@bp.route("/presensi/absen-hp", methods=["GET", "POST"])
@roles("piket", "bk")
def log():
    if request.method == "POST":
        aid = form_int("id")
        aksi = request.form.get("aksi")
        if aksi == "batal" and aid:
            ok, pesan = svc.batalkan(aid, g.user["nama"])
            flash(pesan, "success" if ok else "error")
        elif aksi == "periksa" and aid:
            execute("UPDATE absen_hp SET diperiksa = 1 WHERE id = ?", (aid,))
        return redirect(request.full_path if request.args else url_for("absen_hp.log"))
    tgl = arg_date("tanggal", utils.today())
    saring = request.args.get("saring", "")
    where, args = ["date(a.waktu) = ?"], [tgl.isoformat()]
    if saring == "periksa":
        where.append("a.periksa = 1 AND a.diperiksa = 0 AND a.status = 'ok'")
    elif saring == "ditolak":
        where.append("a.status = 'ditolak'")
    rows = query("SELECT a.*, s.nama, s.nis, k.nama AS kelas FROM absen_hp a JOIN siswa s ON s.id = a.siswa_id "
                 f"LEFT JOIN kelas k ON k.id = s.kelas_id WHERE {' AND '.join(where)} ORDER BY a.id DESC", args)
    hitung = query("SELECT SUM(status = 'ok') AS ok, SUM(status = 'ditolak') AS ditolak, "
                   "SUM(periksa = 1 AND diperiksa = 0 AND status = 'ok') AS periksa FROM absen_hp "
                   "WHERE date(waktu) = ?", (tgl.isoformat(),), one=True)
    return render_template("presensi/absen_hp.html", rows=rows, tanggal=tgl, saring=saring,
                           hitung={k: hitung[k] or 0 for k in ("ok", "ditolak", "periksa")})
