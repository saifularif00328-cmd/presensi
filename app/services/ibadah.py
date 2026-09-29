"""Logika tap ibadah (dipakai halaman Tap Ibadah dan perangkat RFID mode ibadah)."""
from .. import utils
from ..db import execute, query
from ..qr import find_siswa, jenis_kartu
from .attendance import _log


def berlaku_pada(ib, d):
    return str(d.isoweekday()) in (ib["hari"] or "").split(",")


def jadwal_hari(d, db=None):
    return [r for r in query("SELECT * FROM ibadah WHERE aktif = 1 ORDER BY jam_mulai", db=db)
            if berlaku_pada(r, d)]


def jadwal_sekarang(waktu=None, db=None):
    """Jadwal yang sedang berlangsung pada `waktu` (None bila tidak ada)."""
    waktu = waktu or utils.now()
    jam = waktu.strftime("%H:%M")
    return next((j for j in jadwal_hari(waktu.date(), db)
                 if j["jam_mulai"][:5] <= jam <= j["jam_selesai"][:5]), None)


def tap(text, ib, db, waktu=None, metode="kamera"):
    """Catat tap ibadah. Mengembalikan dict hasil (format sama dengan scan presensi)."""
    if ib is None:
        return {"ok": False, "level": "error", "pesan": "Tidak ada jadwal ibadah saat ini"}
    if metode in ("scanner", "kamera") and jenis_kartu(text) == "rfid":
        metode = "rfid"
    waktu = waktu or utils.now()
    siswa, err = find_siswa(text, db=db)
    if siswa is None:
        db.commit()  # simpan catatan kartu tak dikenal
        return {"ok": False, "level": "error", "pesan": err}
    info = {"siswa": {"id": siswa["id"], "nama": siswa["nama"], "kelas": siswa["kelas_nama"],
                      "foto": siswa["foto"]}}
    if ib["jk"] and siswa["jk"] and ib["jk"] != siswa["jk"]:
        return {**info, "ok": False, "level": "warning",
                "pesan": f"{ib['nama']} tidak berlaku untuk siswa ini"}
    tgl, jam = waktu.date().isoformat(), waktu.strftime("%H:%M:%S")
    ada = query("SELECT jam FROM presensi_ibadah WHERE siswa_id = ? AND ibadah_id = ? AND "
                "tanggal = ?", (siswa["id"], ib["id"], tgl), one=True, db=db)
    if ada:
        return {**info, "ok": False, "level": "warning",
                "pesan": f"Sudah tap {ib['nama']} pukul {ada['jam'][:5]}"}
    execute("INSERT INTO presensi_ibadah(siswa_id, ibadah_id, tanggal, jam) VALUES (?,?,?,?)",
            (siswa["id"], ib["id"], tgl, jam), db=db, commit=False)
    _log(db, siswa["id"], "ibadah", ib["nama"], f"Tap {ib['nama']} berhasil", metode, waktu)
    db.commit()
    return {**info, "ok": True, "level": "success", "jam": jam[:5],
            "pesan": f"Tap {ib['nama']} berhasil"}
