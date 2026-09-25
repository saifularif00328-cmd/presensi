"""Definisi menu grid Beranda (dikelompokkan per kategori)."""
from flask import url_for

from .auth import can
from .db import get_setting
from .license import TIER_LABEL, has_feature, min_tier

# (label, ikon, endpoint, roles yang boleh selain admin, fitur lisensi)
MENU = [
    ("Data Master", [
        ("Data Kelas", "🏫", "master.kelas", (), "master"),
        ("Data Siswa", "🎓", "master.siswa", (), "master"),
        ("Data Guru", "👩‍🏫", "master.guru", (), "master"),
        ("Tahun Ajaran", "📅", "master.tahun_ajaran", (), "master"),
    ]),
    ("Presensi", [
        ("Scan QR", "📷", "presensi.scan", ("piket",), "presensi"),
        ("Monitor Live", "📡", "presensi.monitor", ("piket", "bk"), "presensi"),
        ("Presensi Manual", "✍️", "presensi.manual", ("piket",), "presensi"),
        ("Rekap Presensi", "📊", "presensi.rekap", ("piket", "bk"), "rekap"),
        ("SMT Presensi", "🗂️", "presensi.smt", ("piket", "bk"), "rekap"),
        ("Cetak Kartu", "🪪", "master.kartu", (), "kartu"),
    ]),
    ("Perizinan", [
        ("Izin & Sakit", "🤒", "perizinan.izin", ("piket", "bk"), "perizinan"),
        ("Izin Keluar", "🚪", "perizinan.keluar", ("piket", "bk"), "perizinan"),
        ("Pengajuan Kartu", "🔁", "perizinan.kartu", ("piket",), "perizinan"),
    ]),
    ("Ibadah", [
        ("Daftar Ibadah", "🕌", "ibadah.daftar", (), "ibadah"),
        ("Tap Ibadah", "👆", "ibadah.tap", ("piket", "bk"), "ibadah"),
        ("Rekap Ibadah", "📋", "ibadah.rekap", ("piket", "bk"), "ibadah"),
        ("SMT Ibadah", "🗃️", "ibadah.smt", ("piket", "bk"), "ibadah"),
    ]),
    ("Kedisiplinan", [
        ("Tata Tertib", "📜", "kedisiplinan.tatib", ("piket", "bk"), "presensi"),
        ("Rekap Pelanggaran", "⚠️", "kedisiplinan.pelanggaran", ("bk",), "pelanggaran"),
        ("Aturan Jam", "⏰", "kedisiplinan.aturan_jam", (), "presensi"),
    ]),
    ("Sistem", [
        ("Kalender Libur", "🏖️", "sistem.libur", (), "presensi"),
        ("Akses User", "🔐", "sistem.users", (), "multiuser"),
        ("Info", "📢", "sistem.info", ("piket", "bk"), "presensi"),
        ("Pengaturan", "⚙️", "sistem.pengaturan", (), "presensi"),
        ("Notifikasi WA", "💬", "notifikasi.pengaturan", (), "whatsapp"),
        ("Log Notifikasi", "🧾", "notifikasi.log", (), "whatsapp"),
        ("Multi-Cabang", "🌐", "sistem.cabang", (), "multicabang"),
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
            groups.append({"title": title, "items": out})
    return groups
