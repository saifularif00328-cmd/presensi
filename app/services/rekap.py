"""Perhitungan rekap presensi harian, rentang tanggal, dan semester."""
from .. import utils
from ..db import query


def rekap_kelas_hari(db, tgl):
    """Angka H/I/S/A/D per kelas untuk satu tanggal (kartu di Beranda)."""
    rows = query(
        "SELECT k.id, k.nama, k.jenjang, "
        "(SELECT COUNT(*) FROM siswa s WHERE s.kelas_id = k.id AND s.aktif = 1) AS total, "
        "SUM(p.keterangan = 'H') AS H, SUM(p.keterangan = 'I') AS I, "
        "SUM(p.keterangan = 'S') AS S, SUM(p.keterangan = 'A') AS A, "
        "SUM(p.keterangan = 'D') AS D, SUM(p.status_masuk = 'Telat') AS telat "
        "FROM kelas k LEFT JOIN presensi p ON p.kelas_id = k.id AND p.tanggal = ? "
        "GROUP BY k.id ORDER BY k.jenjang, k.nama", (tgl,), db=db)
    out = []
    for r in rows:
        d = dict(r)
        for key in ("H", "I", "S", "A", "D", "telat"):
            d[key] = d[key] or 0
        d["belum"] = max(d["total"] - d["H"] - d["I"] - d["S"] - d["A"] - d["D"], 0)
        out.append(d)
    return out


def rekap_semester(db, start, end, kelas_id=None):
    """Rekap per siswa dalam rentang tanggal: jumlah H/I/S/A/D, telat, % kehadiran."""
    end_eff = min(end, utils.today())
    efektif = utils.school_days(start, end_eff, db=db) if end_eff >= start else []
    n_efektif = len(efektif)
    where, args = "s.aktif = 1", [start.isoformat(), end_eff.isoformat()]
    if kelas_id:
        where += " AND s.kelas_id = ?"
        args.append(kelas_id)
    rows = query(
        "SELECT s.id, s.nis, s.nama, k.nama AS kelas, "
        "COUNT(p.id) AS tercatat, "
        "SUM(p.keterangan = 'H') AS H, SUM(p.keterangan = 'I') AS I, "
        "SUM(p.keterangan = 'S') AS S, SUM(p.keterangan = 'A') AS A, "
        "SUM(p.keterangan = 'D') AS D, SUM(p.status_masuk = 'Telat') AS telat, "
        "SUM(p.status_pulang = 'Pulang Cepat') AS pulang_cepat, "
        "SUM(p.status_pulang = 'Belum Pulang') AS belum_pulang "
        "FROM siswa s LEFT JOIN kelas k ON k.id = s.kelas_id "
        "LEFT JOIN presensi p ON p.siswa_id = s.id AND p.tanggal BETWEEN ? AND ? "
        f"WHERE {where} GROUP BY s.id ORDER BY k.nama, s.nama", args, db=db)
    out = []
    for r in rows:
        d = dict(r)
        for key in ("H", "I", "S", "A", "D", "telat", "pulang_cepat", "belum_pulang"):
            d[key] = d[key] or 0
        d["efektif"] = n_efektif
        d["persen"] = round((d["H"] + d["D"]) * 100 / n_efektif, 1) if n_efektif else 0
        out.append(d)
    return out, n_efektif
