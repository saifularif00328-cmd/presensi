"""Definisi menu grid Beranda (dikelompokkan per kategori)."""
from flask import url_for

from .auth import can
from .db import get_setting
from .license import TIER_LABEL, has_feature, min_tier

# (label, ikon Lucide di static/icons.svg, endpoint, roles selain admin, fitur lisensi)
TONE = {"Data Master": "blue", "Presensi": "green", "Perizinan": "amber", "Ibadah": "violet",
        "Kedisiplinan": "rose", "Sistem": "slate"}

MENU = [
    ("Data Master", [
        ("Data Kelas", "kelas", "master.kelas", (), "master"),
        ("Data Siswa", "siswa", "master.siswa", (), "master"),
        ("Data Guru", "guru", "master.guru", (), "master"),
        ("Tahun Ajaran", "tahun", "master.tahun_ajaran", (), "master"),
    ]),
    ("Presensi", [
        ("Scan QR", "scan", "presensi.scan", ("piket",), "presensi"),
        ("Monitor Live", "monitor", "presensi.monitor", ("piket", "bk"), "presensi"),
        ("Presensi Manual", "manual", "presensi.manual", ("piket",), "presensi"),
        ("Rekap Presensi", "rekap", "presensi.rekap", ("piket", "bk"), "rekap"),
        ("SMT Presensi", "smt", "presensi.smt", ("piket", "bk"), "rekap"),
        ("Cetak Kartu", "kartu", "master.kartu", (), "kartu"),
    ]),
    ("Perizinan", [
        ("Izin & Sakit", "izin", "perizinan.izin", ("piket", "bk"), "perizinan"),
        ("Izin Keluar", "keluar", "perizinan.keluar", ("piket", "bk"), "perizinan"),
        ("Pengajuan Kartu", "kartu-ulang", "perizinan.kartu", ("piket",), "perizinan"),
    ]),
    ("Ibadah", [
        ("Daftar Ibadah", "ibadah", "ibadah.daftar", (), "ibadah"),
        ("Tap Ibadah", "tap", "ibadah.tap", ("piket", "bk"), "ibadah"),
        ("Rekap Ibadah", "rekap-ibadah", "ibadah.rekap", ("piket", "bk"), "ibadah"),
        ("SMT Ibadah", "smt-ibadah", "ibadah.smt", ("piket", "bk"), "ibadah"),
    ]),
    ("Kedisiplinan", [
        ("Tata Tertib", "tatib", "kedisiplinan.tatib", ("piket", "bk"), "presensi"),
        ("Rekap Pelanggaran", "pelanggaran", "kedisiplinan.pelanggaran", ("bk",), "pelanggaran"),
        ("Aturan Jam", "jam", "kedisiplinan.aturan_jam", (), "presensi"),
    ]),
    ("Sistem", [
        ("Kalender Libur", "libur", "sistem.libur", (), "presensi"),
        ("Akses User", "user-akses", "sistem.users", (), "multiuser"),
        ("Info", "info", "sistem.info", ("piket", "bk"), "presensi"),
        ("Pengaturan", "pengaturan", "sistem.pengaturan", (), "presensi"),
        ("Notifikasi WA", "wa", "notifikasi.pengaturan", (), "whatsapp"),
        ("Log Notifikasi", "log", "notifikasi.log", (), "whatsapp"),
        ("Multi-Cabang", "cabang", "sistem.cabang", (), "multicabang"),
    ]),
]


def build_menu():
    ibadah_on = get_setting("modul_ibadah_aktif") == "1"
    groups = []
    for title, items in MENU:
        if title == "Ibadah" and not ibadah_on:
            continue
        out = []
        for label, icon, endpoint, roles, feat in items:
            if not can(*roles):
                continue
            locked = not has_feature(feat)
            out.append({"label": label, "icon": icon, "url": url_for(endpoint),
                        "locked": locked, "tier": TIER_LABEL[min_tier(feat)] if locked else ""})
        if out:
            groups.append({"title": title, "tone": TONE.get(title, "blue"), "items": out})
    return groups
