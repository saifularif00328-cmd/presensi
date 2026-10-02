"""Lokasi data & berkas konfigurasi Presensiku Pos."""
import json
import os
import sys

PORT = 8765


def folder_data():
    d = os.environ.get("PRESENSIKU_POS_DATA")
    if not d:
        if os.name == "nt":
            d = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "PresensikuPos")
        else:
            d = os.path.join(os.path.expanduser("~"), ".presensiku-pos")
    os.makedirs(d, exist_ok=True)
    return d


def jalur(*bagian):
    return os.path.join(folder_data(), *bagian)


def baca(nama, bawaan=None):
    try:
        with open(jalur(nama), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {} if bawaan is None else bawaan


def tulis(nama, data, rahasia=False):
    p = jalur(nama)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    if rahasia and os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def sumber_statis(nama):
    """Berkas layar (layar_gerbang.js/css) — dari bundel PyInstaller atau dari repo."""
    dasar = getattr(sys, "_MEIPASS", None)
    calon = []
    if dasar:
        calon.append(os.path.join(dasar, "statis", nama))
    sini = os.path.dirname(os.path.abspath(__file__))
    calon.append(os.path.join(sini, "web", nama))
    repo = os.path.join(sini, "..", "..", "app")
    if nama.endswith(".html"):
        calon.append(os.path.join(repo, "templates", "presensi", nama))
    else:
        calon.append(os.path.join(repo, "static", "js" if nama.endswith(".js") else "css", nama))
    for c in calon:
        if os.path.exists(c):
            return c
    return None


def normal_server(teks):
    """'presensiku.biz.id/smpn1' -> 'https://presensiku.biz.id/smpn1'."""
    t = (teks or "").strip().rstrip("/")
    if t and not t.startswith(("http://", "https://")):
        t = "https://" + t
    return t
