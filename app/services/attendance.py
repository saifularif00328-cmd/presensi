"""Logika inti presensi: scan masuk/pulang, aturan jam, tutup harian."""
from datetime import timedelta

from .. import utils
from ..db import execute, query
from ..qr import find_siswa
from . import notify

MODES = ("auto", "masuk", "pulang")


def aturan_for(kelas_id, jenjang=None, db=None):
    """Aturan jam yang berlaku: khusus kelas > khusus jenjang > default."""
    if kelas_id:
        r = query("SELECT * FROM aturan_jam WHERE kelas_id = ? ORDER BY id LIMIT 1",
                  (kelas_id,), one=True, db=db)
        if r:
            return r
    if jenjang:
        r = query("SELECT * FROM aturan_jam WHERE kelas_id IS NULL AND jenjang = ? "
                  "ORDER BY id LIMIT 1", (jenjang,), one=True, db=db)
        if r:
            return r
    r = query("SELECT * FROM aturan_jam WHERE kelas_id IS NULL AND "
              "(jenjang IS NULL OR jenjang = '') ORDER BY id LIMIT 1", one=True, db=db)
    if r:
        return r
    return {"jam_masuk": "07:00", "batas_telat": "07:15", "batas_pulang_cepat": "11:00",
            "jam_pulang": "14:00", "jam_tutup": "16:00"}


def _t(s):
    """'HH:MM' → 'HH:MM:SS' agar bisa dibandingkan sebagai string."""
    return s if len(s) == 8 else f"{s}:00"


def status_masuk(jam, aturan):
    return "Telat" if jam > _t(aturan["batas_telat"]) else "Hadir"


def status_pulang(jam, aturan):
    return "Pulang Cepat" if jam < _t(aturan["jam_pulang"]) else "Tepat Waktu"


def _siswa_dict(s):
    return {"id": s["id"], "nama": s["nama"], "kelas": s["kelas_nama"] or "-",
            "nis": s["nis"] or "", "foto": s["foto"]}


def _log(db, siswa_id, jenis, status, pesan, metode):
    execute("INSERT INTO scan_log(siswa_id, waktu, jenis, status, pesan, metode) "
            "VALUES (?,?,?,?,?,?)",
            (siswa_id, utils.now().strftime("%Y-%m-%d %H:%M:%S"), jenis, status, pesan, metode),
            db=db, commit=False)


def process_scan(text, mode="auto", metode="scanner", db=None):
    """Proses satu hasil scan QR. Selalu mengembalikan dict hasil untuk UI."""
    from ..db import get_db
    db = db or get_db()
    mode = mode if mode in MODES else "auto"
    siswa, err = find_siswa(text, db=db)
    if siswa is None:
        _log(db, None, "gagal", None, err, metode)
        db.commit()
        return {"ok": False, "level": "error", "pesan": err}

    now = utils.now()
    tgl = now.date()
    if not utils.is_school_day(tgl, db=db):
        ket = utils.libur_on(tgl, db=db) or "bukan hari sekolah"
        return {"ok": False, "level": "error", "siswa": _siswa_dict(siswa),
                "pesan": f"Presensi dilewati: hari ini libur ({ket})"}

    jam = now.strftime("%H:%M:%S")
    aturan = aturan_for(siswa["kelas_id"], siswa["jenjang"], db=db)
    rec = query("SELECT * FROM presensi WHERE siswa_id = ? AND tanggal = ?",
                (siswa["id"], tgl.isoformat()), one=True, db=db)
    sudah_masuk = rec is not None and rec["jam_masuk"]
    sudah_pulang = rec is not None and rec["jam_pulang"]

    if mode == "auto":
        if not sudah_masuk:
            mode = "masuk"
        elif not sudah_pulang and jam >= _t(aturan["batas_pulang_cepat"]):
            mode = "pulang"
        else:
            mode = "ulang"

    base = {"siswa": _siswa_dict(siswa), "jam": jam[:5]}

    if mode == "ulang" or (mode == "masuk" and sudah_masuk) or (mode == "pulang" and sudah_pulang):
        if sudah_pulang:
            pesan = f"Sudah absen pulang pukul {rec['jam_pulang'][:5]}"
        else:
            pesan = f"Sudah absen masuk pukul {rec['jam_masuk'][:5]}"
        _log(db, siswa["id"], "peringatan", None, pesan, metode)
        db.commit()
        return {**base, "ok": False, "level": "warning", "jenis": "ulang", "pesan": pesan}

    if mode == "pulang" and not sudah_masuk:
        pesan = "Belum absen masuk hari ini — tidak bisa absen pulang"
        _log(db, siswa["id"], "peringatan", None, pesan, metode)
        db.commit()
        return {**base, "ok": False, "level": "warning", "jenis": "pulang", "pesan": pesan}

    if mode == "masuk":
        st = status_masuk(jam, aturan)
        if rec is None:
            execute("INSERT INTO presensi(siswa_id, kelas_id, tanggal, jam_masuk, status_masuk, "
                    "keterangan, sumber) VALUES (?,?,?,?,?, 'H', 'scan')",
                    (siswa["id"], siswa["kelas_id"], tgl.isoformat(), jam, st), db=db, commit=False)
        else:
            # Sebelumnya tercatat I/S/A tetapi siswa ternyata datang → jadi Hadir
            execute("UPDATE presensi SET jam_masuk = ?, status_masuk = ?, keterangan = 'H', "
                    "sumber = 'scan', updated_at = datetime('now','localtime') WHERE id = ?",
                    (jam, st, rec["id"]), db=db, commit=False)
        pesan = f"Absen masuk berhasil — {st}"
        _log(db, siswa["id"], "masuk", st, pesan, metode)
        notify.enqueue(db, siswa, "masuk", {"jam": jam[:5], "status": st})
        db.commit()
        return {**base, "ok": True, "level": "success" if st == "Hadir" else "warning",
                "jenis": "masuk", "status": st, "pesan": pesan}

    # mode == "pulang"
    st = status_pulang(jam, aturan)
    execute("UPDATE presensi SET jam_pulang = ?, status_pulang = ?, "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (jam, st, rec["id"]), db=db, commit=False)
    pesan = f"Absen pulang berhasil — {st}"
    _log(db, siswa["id"], "pulang", st, pesan, metode)
    notify.enqueue(db, siswa, "pulang", {"jam": jam[:5], "status": st})
    db.commit()
    return {**base, "ok": True, "level": "success" if st == "Tepat Waktu" else "warning",
            "jenis": "pulang", "status": st, "pesan": pesan}


def set_manual(db, siswa_id, tanggal, keterangan, jam_masuk=None, jam_pulang=None,
               catatan=None):
    """Presensi manual oleh admin/guru piket (menimpa data hari itu)."""
    siswa = query("SELECT s.*, k.jenjang FROM siswa s LEFT JOIN kelas k ON k.id = s.kelas_id "
                  "WHERE s.id = ?", (siswa_id,), one=True, db=db)
    if siswa is None:
        raise ValueError("Siswa tidak ditemukan")
    aturan = aturan_for(siswa["kelas_id"], siswa["jenjang"], db=db)
    jm = _t(jam_masuk) if jam_masuk else None
    jp = _t(jam_pulang) if jam_pulang else None
    if keterangan != "H":
        jm = jp = None
    sm = status_masuk(jm, aturan) if jm else None
    sp = status_pulang(jp, aturan) if jp else None
    execute("INSERT INTO presensi(siswa_id, kelas_id, tanggal, jam_masuk, status_masuk, "
            "jam_pulang, status_pulang, keterangan, sumber, catatan) "
            "VALUES (?,?,?,?,?,?,?,?, 'manual', ?) "
            "ON CONFLICT(siswa_id, tanggal) DO UPDATE SET jam_masuk = excluded.jam_masuk, "
            "status_masuk = excluded.status_masuk, jam_pulang = excluded.jam_pulang, "
            "status_pulang = excluded.status_pulang, keterangan = excluded.keterangan, "
            "sumber = 'manual', catatan = excluded.catatan, "
            "updated_at = datetime('now','localtime')",
            (siswa_id, siswa["kelas_id"], tanggal, jm, sm, jp, sp, keterangan, catatan),
            db=db, commit=False)
    _log(db, siswa_id, "manual", utils.KETERANGAN.get(keterangan),
         f"Presensi manual {tanggal}: {utils.KETERANGAN.get(keterangan)}", "manual")
    db.commit()


def apply_izin(db, izin):
    """Tandai hari-hari efektif dalam rentang izin yang disetujui sebagai I/S/D.

    Data 'Hadir' (sudah scan) tidak ditimpa."""
    ket = {"Izin": "I", "Sakit": "S", "Dispensasi": "D"}.get(izin["jenis"], "I")
    siswa = query("SELECT kelas_id FROM siswa WHERE id = ?", (izin["siswa_id"],), one=True, db=db)
    start = utils.parse_date(izin["tanggal_mulai"])
    end = utils.parse_date(izin["tanggal_selesai"])
    for d in utils.school_days(start, end, db=db):
        execute("INSERT INTO presensi(siswa_id, kelas_id, tanggal, keterangan, sumber, catatan) "
                "VALUES (?,?,?,?, 'izin', ?) ON CONFLICT(siswa_id, tanggal) DO UPDATE SET "
                "keterangan = excluded.keterangan, sumber = 'izin', catatan = excluded.catatan, "
                "updated_at = datetime('now','localtime') "
                "WHERE presensi.jam_masuk IS NULL",
                (izin["siswa_id"], siswa["kelas_id"] if siswa else None, d.isoformat(), ket,
                 izin["alasan"]), db=db, commit=False)


def close_day(db, tgl=None, force=False, kirim_notif=True):
    """Proses tutup harian per kelas setelah jam_tutup:
    - sudah masuk tapi belum pulang → 'Belum Pulang'
    - tidak ada catatan sama sekali → Alpha (A) + notifikasi ke orang tua
    Idempoten: tiap (tanggal, kelas) hanya diproses sekali."""
    tgl = tgl or utils.today()
    if not utils.is_school_day(tgl, db=db):
        return 0
    now = utils.now()
    jam = now.strftime("%H:%M:%S")
    total = 0
    kelas_rows = query("SELECT id, jenjang FROM kelas", db=db)
    for k in kelas_rows:
        if query("SELECT 1 FROM tutup_harian WHERE tanggal = ? AND kelas_id = ?",
                 (tgl.isoformat(), k["id"]), one=True, db=db):
            continue
        aturan = aturan_for(k["id"], k["jenjang"], db=db)
        if not force and tgl == now.date() and jam < _t(aturan["jam_tutup"]):
            continue
        execute("UPDATE presensi SET status_pulang = 'Belum Pulang' WHERE tanggal = ? "
                "AND kelas_id = ? AND jam_masuk IS NOT NULL AND jam_pulang IS NULL",
                (tgl.isoformat(), k["id"]), db=db, commit=False)
        absen = query("SELECT s.*, k.nama AS kelas_nama FROM siswa s "
                      "JOIN kelas k ON k.id = s.kelas_id WHERE s.kelas_id = ? "
                      "AND s.aktif = 1 AND date(s.created_at) <= ? AND NOT EXISTS ("
                      "SELECT 1 FROM presensi p WHERE p.siswa_id = s.id AND p.tanggal = ?)",
                      (k["id"], tgl.isoformat(), tgl.isoformat()), db=db)
        for s in absen:
            execute("INSERT INTO presensi(siswa_id, kelas_id, tanggal, keterangan, sumber) "
                    "VALUES (?,?,?, 'A', 'otomatis')", (s["id"], k["id"], tgl.isoformat()),
                    db=db, commit=False)
            if kirim_notif and tgl == now.date():
                notify.enqueue(db, s, "alpha", {"jam": jam[:5], "status": "Alpha"})
            total += 1
        execute("INSERT INTO tutup_harian(tanggal, kelas_id) VALUES (?, ?)",
                (tgl.isoformat(), k["id"]), db=db, commit=False)
    db.commit()
    return total


def catch_up(db, days=7):
    """Jalankan tutup harian untuk hari-hari sebelumnya yang terlewat
    (mis. komputer mati sebelum jam tutup). Tanpa kirim notifikasi."""
    for i in range(days, 0, -1):
        close_day(db, utils.today() - timedelta(days=i), force=True, kirim_notif=False)
