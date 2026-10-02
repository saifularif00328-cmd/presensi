"""Absen dari HP siswa: lokasi GPS (radius sekolah / lokasi kegiatan) + foto bukti.

Pengaman:
- metode HP harus diaktifkan sekolah, siswa harus termasuk cakupan (semua / kelas tertentu /
  sasaran lokasi kegiatan yang sedang berlangsung);
- token sekali pakai berlaku 2 menit (diambil tepat sebelum absen);
- satu akun siswa terikat ke satu HP, dan satu HP tidak bisa dipakai siswa lain (titip absen);
- akurasi GPS dibatasi, jarak dihitung di server (haversine), foto selfie wajib;
- kejanggalan (GPS kurang akurat, di tepi radius, HP baru, posisi GPS lama) ditandai
  "perlu diperiksa" untuk admin, yang bisa membatalkan absen.
- pencocokan wajah (opsional, setting `hp_wajah`): selfie dicocokkan dengan data acuan siswa
  di server + tantangan tengok kiri/kanan; mode "tandai" hanya menandai, "wajib" menolak.
Aplikasi GPS palsu tidak bisa dicegah 100% dari browser; foto bukti, pencocokan wajah, dan
tinjauan admin menjadi pengaman tambahan.
"""
import hashlib
import io
import os
import secrets
from datetime import timedelta

from PIL import Image, ImageOps

from .. import config, utils
from ..db import execute, get_setting, query
from . import wajah
from .attendance import metode_aktif, process_scan

TOKEN_DETIK = 120
UMUR_GPS_MAKS = 60_000         # ms; posisi lebih lama dari ini ditandai


def _fmt(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def _ids(teks):
    return {int(x) for x in (teks or "").replace(" ", "").split(",") if x.isdigit()}


def siswa_lengkap(siswa_id, db=None):
    return query("SELECT s.*, k.nama AS kelas_nama, k.jenjang FROM siswa s LEFT JOIN kelas k "
                 "ON k.id = s.kelas_id WHERE s.id = ? AND s.aktif = 1", (siswa_id,), one=True, db=db)


def lokasi_berlaku(siswa, tanggal=None, db=None):
    """Lokasi yang boleh dipakai siswa ini pada tanggal tsb (sekolah + kegiatan sasaran)."""
    tgl = (tanggal or utils.today()).isoformat()
    hasil = []
    for r in query("SELECT * FROM lokasi_absen WHERE aktif = 1 ORDER BY jenis DESC, nama", db=db):
        if r["jenis"] == "kegiatan":
            if (r["mulai"] and str(r["mulai"]) > tgl) or (r["selesai"] and str(r["selesai"]) < tgl):
                continue
            kelas, siswa_ids = _ids(r["kelas_ids"]), _ids(r["siswa_ids"])
            if (kelas or siswa_ids) and siswa["kelas_id"] not in kelas and siswa["id"] not in siswa_ids:
                continue
        hasil.append(r)
    return hasil


def boleh(siswa, tanggal=None, db=None):
    """(boleh, alasan, lokasi). Sasaran lokasi kegiatan selalu boleh walau kelasnya tidak
    termasuk cakupan (mis. siswa PKL)."""
    if not metode_aktif("hp", db=db):
        return False, "Absen dari HP tidak diaktifkan sekolah.", []
    lokasi = lokasi_berlaku(siswa, tanggal, db)
    if not lokasi:
        return False, "Belum ada lokasi absen yang berlaku untuk Anda hari ini.", []
    if (get_setting("hp_cakupan", db=db) or "semua") == "kelas":
        kegiatan = any(r["jenis"] == "kegiatan" and (_ids(r["kelas_ids"]) or _ids(r["siswa_ids"]))
                       for r in lokasi)
        if siswa["kelas_id"] not in _ids(get_setting("hp_kelas", db=db)) and not kegiatan:
            return False, "Kelas Anda belum diizinkan absen dari HP.", []
    if mode_wajah(db) == "wajib" and not wajah.siap(siswa["id"], db):
        return False, ("Data wajah Anda belum terdaftar (perlu persetujuan orang tua & foto wajah). "
                       "Hubungi wali kelas / admin."), []
    return True, "", lokasi


def mode_wajah(db=None):
    m = get_setting("hp_wajah", db=db) or "mati"
    return m if m in ("tandai", "wajib") else "mati"


def pakai_tantangan(db=None):
    return mode_wajah(db) != "mati" and (get_setting("wajah_tantangan", db=db) or "1") == "1"


def buat_token(siswa_id, db=None):
    """Token sekali pakai + tantangan tengok (bila pencocokan wajah aktif)."""
    t = secrets.token_urlsafe(32)
    tantangan = wajah.buat_tantangan() if pakai_tantangan(db) else None
    execute("INSERT INTO absen_hp_token(token, siswa_id, dibuat, tantangan) VALUES (?,?,?,?)",
            (t, siswa_id, _fmt(utils.now()), tantangan), db=db)
    execute("DELETE FROM absen_hp_token WHERE dibuat < ?",
            (_fmt(utils.now() - timedelta(days=1)),), db=db)
    return {"token": t, "tantangan": tantangan}


def _pakai_token(token, siswa_id, db=None):
    """Baris token bila sah (lalu ditandai terpakai), None bila tidak."""
    r = query("SELECT * FROM absen_hp_token WHERE token = ?", (token or "",), one=True, db=db)
    if r is None or r["siswa_id"] != siswa_id or r["dipakai"]:
        return None
    if utils.parse_datetime(r["dibuat"]) < utils.now() - timedelta(seconds=TOKEN_DETIK):
        return None
    execute("UPDATE absen_hp_token SET dipakai = 1 WHERE token = ?", (token,), db=db)
    return r


def _hash(t):
    return hashlib.sha256((t or "").encode()).hexdigest()


def cek_hp(siswa_id, token_hp, info, db=None):
    """(ok, baru, pesan). Mengikat akun ke HP saat pertama kali; `baru` = didaftarkan hari ini."""
    if not token_hp or len(token_hp) < 32 or len(token_hp) > 128:
        return False, False, "Identitas HP tidak terbaca. Muat ulang halaman."
    h = _hash(token_hp)
    lain = query("SELECT siswa_id FROM hp_siswa WHERE token_hash = ? AND siswa_id <> ?",
                 (h, siswa_id), one=True, db=db)
    if lain:
        return False, False, "HP ini sudah terdaftar untuk siswa lain. Absen harus dari HP sendiri."
    r = query("SELECT * FROM hp_siswa WHERE siswa_id = ?", (siswa_id,), one=True, db=db)
    now = _fmt(utils.now())
    if r is None:
        execute("INSERT INTO hp_siswa(siswa_id, token_hash, info, dibuat, terakhir) VALUES (?,?,?,?,?)",
                (siswa_id, h, (info or "")[:200], now, now), db=db)
        return True, True, ""
    if r["token_hash"] != h:
        return False, False, ("Akun Anda terdaftar di HP lain. Bila ganti HP, minta admin / wali kelas "
                              "mereset HP Anda.")
    execute("UPDATE hp_siswa SET terakhir = ? WHERE siswa_id = ?", (now, siswa_id), db=db)
    return True, str(r["dibuat"])[:10] == now[:10], ""     # didaftarkan hari ini = tetap "baru"


def _baca(berkas):
    if not berkas or not berkas.filename:
        return b""
    return berkas.read(8 * 1024 * 1024 + 1)[:8 * 1024 * 1024]


def _simpan_foto(data, siswa_id):
    if not data:
        return None
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:  # noqa: BLE001 — bukan gambar
        return None
    if min(img.size) < 120:
        return None
    img.thumbnail((720, 720))
    bulan = utils.now().strftime("%Y-%m")
    folder = os.path.join(config.UPLOAD_DIR, "absen_hp", bulan)
    os.makedirs(folder, exist_ok=True)
    nama = f"absen_hp/{bulan}/{siswa_id}_{utils.now():%d%H%M%S}_{secrets.token_hex(4)}.jpg"
    img.save(os.path.join(config.UPLOAD_DIR, nama), "JPEG", quality=78)
    return nama


def _angka(nilai, jenis=float):
    try:
        return jenis(nilai)
    except (TypeError, ValueError):
        return None


def proses(siswa_id, form, berkas_foto, ip="", ua="", db=None, berkas_foto2=None):
    """Proses satu absen HP. Mengembalikan dict {ok, level, pesan, ...} untuk tampilan."""
    siswa = siswa_lengkap(siswa_id, db)
    if siswa is None:
        return {"ok": False, "level": "error", "pesan": "Akun siswa tidak aktif."}
    lat, lng = _angka(form.get("lat")), _angka(form.get("lng"))
    akurasi = _angka(form.get("akurasi"))
    umur_gps = _angka(form.get("umur_gps"), int) or 0
    catat = {"siswa_id": siswa_id, "lat": lat, "lng": lng,
             "akurasi": int(akurasi) if akurasi is not None else None, "ip": ip[:45], "ua": ua[:200]}

    def tolak(pesan, **lain):
        _catat(db, {**catat, **lain, "status": "ditolak", "pesan": pesan[:255], "jenis": "-"})
        return {"ok": False, "level": "error", "pesan": pesan}

    ok, alasan, lokasi = boleh(siswa, db=db)
    if not ok:
        return {"ok": False, "level": "error", "pesan": alasan}
    tok = _pakai_token(form.get("token"), siswa_id, db)
    if tok is None:
        return {"ok": False, "level": "error",
                "pesan": "Sesi absen kedaluwarsa (lebih dari 2 menit). Ulangi dari awal."}
    ok_hp, hp_baru, pesan = cek_hp(siswa_id, form.get("perangkat"), ua, db)
    if not ok_hp:
        return tolak(pesan)
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return tolak("Lokasi tidak terbaca. Izinkan akses lokasi lalu coba lagi.")
    maks = int(get_setting("hp_akurasi_maks", db=db) or 100)
    if akurasi is None or akurasi > maks:
        return tolak(f"Sinyal GPS kurang akurat (±{int(akurasi or 0)} m, batas {maks} m). "
                     "Nyalakan GPS/lokasi akurasi tinggi, pindah ke tempat terbuka, lalu coba lagi.")
    jarak, terdekat = min(((utils.jarak_meter(lat, lng, r["lat"], r["lng"]), r) for r in lokasi),
                          key=lambda x: x[0])
    catat.update(jarak=int(jarak), lokasi_id=terdekat["id"], lokasi_nama=terdekat["nama"])
    if jarak > terdekat["radius"]:
        return tolak(f"Anda di luar area absen: ±{int(jarak)} m dari {terdekat['nama']} "
                     f"(batas {terdekat['radius']} m).")
    data_foto = _baca(berkas_foto)
    foto = _simpan_foto(data_foto, siswa_id)
    if not foto:
        return tolak("Foto selfie wajib diambil sebagai bukti.")
    periksa = []
    mode = mode_wajah(db)
    if mode != "mati":
        try:
            v = wajah.verifikasi(siswa_id, data_foto, _baca(berkas_foto2), tok["tantangan"],
                                 "berkas" if form.get("sumber") == "berkas" else "kamera", db)
        except wajah.TidakTersedia:
            v = {"ok": False, "skor": None, "alasan": "pencocokan wajah sedang tidak tersedia"}
        catat["skor_wajah"] = v.get("skor")
        if not v["ok"]:
            if mode == "wajib":
                return tolak(f"{v['alasan']}. Ulangi dengan wajah terlihat jelas.", foto=foto)
            periksa.append(f"wajah: {v['alasan']}")
        elif v.get("tipis"):
            periksa.append(f"kemiripan wajah tipis ({v['skor']:.2f})")
    if akurasi > maks / 2:
        periksa.append(f"GPS kurang akurat (±{int(akurasi)} m)")
    if jarak > terdekat["radius"] * 0.8:
        periksa.append("di tepi area absen")
    if hp_baru:
        periksa.append("HP baru didaftarkan")
    if umur_gps > UMUR_GPS_MAKS:
        periksa.append(f"posisi GPS {umur_gps // 1000} detik lalu")
    res = process_scan(None, "auto", "hp", db=db, siswa_row=siswa,
                       gerbang=f"HP · {terdekat['nama']}"[:60])
    _catat(db, {**catat, "foto": foto, "jenis": res.get("jenis") or "-",
                "status": "ok" if res.get("ok") else "ditolak", "pesan": (res.get("pesan") or "")[:255],
                "periksa": 1 if periksa and res.get("ok") else 0, "alasan_periksa": ", ".join(periksa)})
    return {**res, "lokasi": terdekat["nama"], "jarak": int(jarak)}


def _catat(db, d):
    kolom = ["siswa_id", "waktu", "lat", "lng", "akurasi", "jarak", "lokasi_id", "lokasi_nama", "foto",
             "jenis", "status", "pesan", "periksa", "alasan_periksa", "skor_wajah", "ip", "ua"]
    d = {**d, "waktu": _fmt(utils.now())}
    execute(f"INSERT INTO absen_hp({', '.join(kolom)}) VALUES ({', '.join('?' for _ in kolom)})",
            tuple(d.get(k) if k not in ("periksa",) else (d.get(k) or 0) for k in kolom), db=db)


def batalkan(absen_id, oleh, db=None):
    """Batalkan absen HP yang sudah tercatat. Mengembalikan (ok, pesan)."""
    a = query("SELECT * FROM absen_hp WHERE id = ?", (absen_id,), one=True, db=db)
    if a is None or a["status"] != "ok" or a["jenis"] not in ("masuk", "pulang"):
        return False, "Absen ini tidak bisa dibatalkan."
    tgl = utils.parse_datetime(a["waktu"]).date().isoformat()
    p = query("SELECT * FROM presensi WHERE siswa_id = ? AND tanggal = ?", (a["siswa_id"], tgl),
              one=True, db=db)
    if p is None:
        return False, "Data presensi sudah tidak ada."
    if a["jenis"] == "masuk":
        if p["jam_pulang"]:
            return False, "Siswa sudah absen pulang. Batalkan absen pulangnya dulu."
        execute("DELETE FROM presensi WHERE id = ?", (p["id"],), db=db, commit=False)
    else:
        execute("UPDATE presensi SET jam_pulang = NULL, status_pulang = NULL, gerbang_pulang = NULL, "
                "updated_at = NOW() WHERE id = ?", (p["id"],), db=db, commit=False)
    execute("UPDATE absen_hp SET status = 'batal', diperiksa = 1 WHERE id = ?", (absen_id,), db=db,
            commit=False)
    execute("INSERT INTO scan_log(siswa_id, waktu, jenis, status, pesan, metode, gerbang) "
            "VALUES (?,?,?,?,?,?,?)",
            (a["siswa_id"], _fmt(utils.now()), "peringatan", None,
             f"Absen {a['jenis']} dari HP dibatalkan oleh {oleh}", "hp", a["lokasi_nama"]),
            db=db, commit=False)
    from ..db import get_db
    (db or get_db()).commit()
    return True, f"Absen {a['jenis']} dibatalkan."


def bersihkan_foto(db=None):
    """Hapus foto bukti yang lebih lama dari `hp_foto_hari` (data absennya tetap)."""
    hari = int(get_setting("hp_foto_hari", db=db) or 30)
    batas = _fmt(utils.now() - timedelta(days=hari))
    n = 0
    for r in query("SELECT id, foto FROM absen_hp WHERE foto IS NOT NULL AND waktu < ?", (batas,), db=db):
        try:
            os.remove(os.path.join(config.UPLOAD_DIR, r["foto"]))
        except OSError:
            pass
        execute("UPDATE absen_hp SET foto = NULL WHERE id = ?", (r["id"],), db=db)
        n += 1
    return n
