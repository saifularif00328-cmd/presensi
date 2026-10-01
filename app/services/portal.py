"""Logika Portal Siswa & Orang Tua: login OTP WhatsApp / NIS+PIN dan data per siswa."""
import secrets
from datetime import timedelta

import requests
from werkzeug.security import check_password_hash, generate_password_hash

from .. import utils
from ..db import execute, get_setting, query
from . import notify

OTP_MENIT = 5
OTP_MAKS_KIRIM = 3          # per nomor per 15 menit
OTP_MAKS_COBA = 5           # salah kode per OTP


def _fmt(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ orang tua
def anak_dari_nomor(nomor, db=None):
    """Siswa aktif yang nomor WA ayah/ibu/wali-nya sama dengan `nomor` (sudah dinormalisasi)."""
    if not nomor:
        return []
    rows = query("SELECT s.*, k.nama AS kelas_nama FROM siswa s LEFT JOIN kelas k "
                 "ON k.id = s.kelas_id WHERE s.aktif = 1 AND (s.wa_ayah IS NOT NULL OR "
                 "s.wa_ibu IS NOT NULL OR s.wa_wali IS NOT NULL) ORDER BY s.nama", db=db)
    return [r for r in rows if nomor in notify.nomor_ortu(r)]


def kirim_otp(nomor_mentah, ip, db):
    """Buat & kirim OTP. Mengembalikan (ok, pesan). Pesan sengaja sama untuk nomor terdaftar
    maupun tidak, agar portal tidak bisa dipakai menebak nomor orang tua."""
    nomor = utils.normalize_wa(nomor_mentah)
    if not nomor:
        return False, "Nomor WhatsApp tidak valid."
    now = utils.now()
    baru = query("SELECT COUNT(*) AS n FROM portal_otp WHERE nomor = ? AND dibuat >= ?",
                 (nomor, _fmt(now - timedelta(minutes=15))), one=True, db=db)["n"]
    if baru >= OTP_MAKS_KIRIM:
        return False, "Terlalu sering meminta kode. Coba lagi 15 menit lagi."
    umum = ("Bila nomor terdaftar di sekolah, kode masuk portal (8 angka) sudah dikirim lewat "
            "pesan WhatsApp dari sekolah. Kode berlaku 5 menit.")
    if not anak_dari_nomor(nomor, db):
        return True, umum
    # 8 angka: sengaja beda dari kode verifikasi akun WhatsApp (6 angka) agar tidak tertukar
    kode = f"{secrets.randbelow(10 ** 8):08d}"
    execute("INSERT INTO portal_otp(nomor, kode_hash, dibuat, kedaluwarsa, ip) VALUES (?,?,?,?,?)",
            (nomor, generate_password_hash(kode), _fmt(now),
             _fmt(now + timedelta(minutes=OTP_MENIT)), ip), db=db)
    pesan = get_setting("wa_tpl_otp", db=db).format_map(notify._SafeDict(
        {"kode": kode, "sekolah": get_setting("nama_sekolah", db=db)}))
    token = notify.fonnte_token(db)
    terkirim = False
    if token:
        try:
            terkirim, _err = notify.send_one(token, nomor, pesan)
        except requests.RequestException:
            terkirim = False
    if not terkirim:
        # cadangan: lewat antrean (terkirim saat koneksi / token siap)
        execute("INSERT INTO notif_queue(jenis, nomor, pesan) VALUES ('otp', ?, ?)",
                (nomor, pesan), db=db)
    return True, umum


def cek_otp(nomor_mentah, kode, db):
    """Mengembalikan (nomor, pesan_error)."""
    nomor = utils.normalize_wa(nomor_mentah)
    now = _fmt(utils.now())
    otp = query("SELECT * FROM portal_otp WHERE nomor = ? AND dipakai = 0 AND kedaluwarsa >= ? "
                "ORDER BY id DESC LIMIT 1", (nomor, now), one=True, db=db)
    if otp is None:
        return None, "Kode sudah kedaluwarsa atau belum diminta. Minta kode baru."
    if otp["percobaan"] >= OTP_MAKS_COBA:
        return None, "Terlalu banyak kode salah. Minta kode baru."
    if not check_password_hash(otp["kode_hash"], (kode or "").strip()):
        execute("UPDATE portal_otp SET percobaan = percobaan + 1 WHERE id = ?", (otp["id"],),
                db=db)
        return None, "Kode salah."
    execute("UPDATE portal_otp SET dipakai = 1 WHERE id = ?", (otp["id"],), db=db)
    return nomor, None


# ------------------------------------------------------------------ siswa (NIS + PIN)
def buat_pin(siswa_ids, db):
    """PIN acak 6 angka untuk siswa terpilih. Mengembalikan {siswa_id: pin} (tampil sekali)."""
    out = {}
    for sid in siswa_ids:
        pin = f"{secrets.randbelow(1000000):06d}"
        execute("UPDATE siswa SET pin_hash = ?, pin_wajib_ganti = 1 WHERE id = ?",
                (generate_password_hash(pin), sid), db=db, commit=False)
        out[sid] = pin
    db.commit()
    return out


def cek_pin(nis, pin, db):
    """Mengembalikan (siswa, pesan_error)."""
    s = query("SELECT * FROM siswa WHERE nis = ? AND aktif = 1", ((nis or "").strip(),),
              one=True, db=db)
    if s is None or not s["pin_hash"] or not check_password_hash(s["pin_hash"], pin or ""):
        return None, "NIS atau PIN salah."
    return s, None


# ------------------------------------------------------------------ data untuk tampilan
def ringkasan(sid, db, bulan=None):
    """Data portal untuk satu siswa: hari ini, kalender bulan, rekap semester, dll."""
    from ..blueprints.common import semester_aktif
    from .rekap import rekap_semester
    today = utils.today()
    s = query("SELECT s.*, k.nama AS kelas_nama FROM siswa s LEFT JOIN kelas k "
              "ON k.id = s.kelas_id WHERE s.id = ?", (sid,), one=True, db=db)
    hari_ini = query("SELECT * FROM presensi WHERE siswa_id = ? AND tanggal = ?",
                     (sid, today.isoformat()), one=True, db=db)
    # kalender bulan
    tahun, bln = (bulan or (today.year, today.month))
    awal = today.replace(year=tahun, month=bln, day=1)
    akhir = (awal.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    rows = {r["tanggal"]: r for r in query(
        "SELECT * FROM presensi WHERE siswa_id = ? AND tanggal BETWEEN ? AND ?",
        (sid, awal.isoformat(), akhir.isoformat()), db=db)}
    libur = {r["tanggal"]: r["keterangan"] for r in query(
        "SELECT tanggal, keterangan FROM libur WHERE tanggal BETWEEN ? AND ?",
        (awal.isoformat(), akhir.isoformat()), db=db)}
    hs = utils.hari_sekolah(db)
    kalender = []
    for d in utils.daterange(awal, akhir):
        iso = d.isoformat()
        p = rows.get(iso)
        if p:
            kode = "T" if p["keterangan"] == "H" and p["status_masuk"] == "Telat" else p["keterangan"]
        elif iso in libur or d.isoweekday() not in hs:
            kode = "L"
        elif d < today:
            kode = "-"
        else:
            kode = ""
        kalender.append({"tanggal": d, "kode": kode, "p": p, "libur": libur.get(iso)})
    # rekap semester
    sem = semester_aktif()
    rekap = None
    if sem:
        rs, _ = rekap_semester(db, utils.parse_date(sem["tanggal_mulai"]),
                               utils.parse_date(sem["tanggal_selesai"]), s["kelas_id"])
        rekap = next((r for r in rs if r["id"] == sid), None)
    pelanggaran = query("SELECT p.*, j.nama AS jenis FROM pelanggaran p LEFT JOIN "
                        "jenis_pelanggaran j ON j.id = p.jenis_id WHERE p.siswa_id = ? "
                        "ORDER BY p.tanggal DESC, p.id DESC LIMIT 20", (sid,), db=db)
    ibadah = query("SELECT pi.tanggal, pi.jam, i.nama FROM presensi_ibadah pi JOIN ibadah i "
                   "ON i.id = pi.ibadah_id WHERE pi.siswa_id = ? ORDER BY pi.tanggal DESC, "
                   "pi.jam DESC LIMIT 10", (sid,), db=db)
    izin = query("SELECT * FROM izin WHERE siswa_id = ? ORDER BY id DESC LIMIT 10", (sid,), db=db)
    info = query("SELECT * FROM info WHERE aktif = 1 ORDER BY penting DESC, id DESC LIMIT 5",
                 db=db)
    return {"s": s, "hari_ini": hari_ini, "kalender": kalender, "awal": awal,
            "rekap": rekap, "sem": sem, "pelanggaran": pelanggaran,
            "poin": sum(p["poin"] for p in pelanggaran), "ibadah": ibadah, "izin": izin,
            "info": info}
