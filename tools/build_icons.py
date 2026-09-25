"""Bangun sprite ikon SVG (app/static/icons.svg) dari paket lucide-static.

Pemakaian (sekali, saat menambah ikon):
    npm pack lucide-static && tar xzf lucide-static-*.tgz
    python tools/build_icons.py package/icons
"""
import os
import re
import sys

# nama di aplikasi -> nama file Lucide
ICONS = {
    "home": "house", "dashboard": "layout-dashboard", "monitor": "activity",
    "siswa": "graduation-cap", "akun": "circle-user-round", "kelas": "school", "guru": "users",
    "tahun": "calendar-range", "scan": "scan-line", "qr": "qr-code", "manual": "square-pen",
    "rekap": "chart-column", "smt": "folder-archive", "kartu": "id-card", "izin": "stethoscope",
    "keluar": "door-open", "kartu-ulang": "refresh-ccw", "ibadah": "moon-star",
    "tap": "fingerprint", "rekap-ibadah": "clipboard-list", "smt-ibadah": "archive",
    "tatib": "scroll-text", "pelanggaran": "triangle-alert", "jam": "alarm-clock",
    "libur": "calendar-off", "user-akses": "shield-check", "info": "megaphone",
    "pengaturan": "settings", "wa": "message-circle", "log": "receipt-text",
    "cabang": "network", "camera": "camera", "webcam": "webcam", "logout": "log-out",
    "login": "log-in", "download": "download", "upload": "upload", "plus": "plus",
    "search": "search", "check": "check", "ok": "circle-check", "err": "circle-x",
    "alert": "circle-alert", "clock": "clock", "back": "chevron-left",
    "next": "chevron-right", "printer": "printer", "trash": "trash-2", "edit": "pencil",
    "eye": "eye", "lock": "lock", "key": "key-round", "save": "save", "refresh": "refresh-cw",
    "excel": "file-spreadsheet", "pdf": "file-text", "user": "user", "database": "database",
    "bell": "bell", "arrow-right": "arrow-right", "logo": "clipboard-check", "menu": "menu",
    "x": "x", "user-check": "user-check", "user-x": "user-x", "wifi": "wifi",
    "wifi-off": "wifi-off", "hourglass": "hourglass", "inbox": "inbox", "sun": "sun",
}


def main(src):
    out = ['<svg xmlns="http://www.w3.org/2000/svg">',
           "<!-- Ikon: Lucide (https://lucide.dev) — lisensi ISC, lihat vendor/lucide.LICENSE -->"]
    for name, fname in ICONS.items():
        svg = open(os.path.join(src, f"{fname}.svg"), encoding="utf-8").read()
        body = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
        body = re.sub(r"\s+", " ", body).strip()
        out.append(f'<symbol id="{name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                   f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</symbol>')
    out.append("</svg>")
    dest = os.path.join(os.path.dirname(__file__), "..", "app", "static", "icons.svg")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"{len(ICONS)} ikon → {os.path.abspath(dest)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "package/icons")
