"""Jalankan Presensiku Pos:  python -m presensiku_pos  (atau PresensikuPos.exe)."""
import argparse
import logging
import logging.handlers
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser

from . import VERSI, konfig


def buka_layar(port):
    """Buka Layar Gerbang di Chrome/Edge mode aplikasi (tanpa bilah alamat)."""
    url = f"http://127.0.0.1:{port}/"
    calon = []
    if os.name == "nt":
        for akar in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            calon += [os.path.join(akar, "Google", "Chrome", "Application", "chrome.exe"),
                      os.path.join(akar, "Microsoft", "Edge", "Application", "msedge.exe")]
    else:
        calon += [shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
    for exe in calon:
        if exe and os.path.exists(exe):
            subprocess.Popen([exe, f"--app={url}", "--start-maximized", "--autoplay-policy=no-user-gesture-required"])
            return
    webbrowser.open(url)


def sudah_berjalan(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="PresensikuPos", description=__doc__)
    ap.add_argument("--port", type=int, default=konfig.PORT)
    ap.add_argument("--tanpa-layar", action="store_true", help="jangan buka browser")
    ap.add_argument("--uji-virtual", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if sudah_berjalan(a.port):                 # instans kedua: cukup buka layarnya
        if not a.tanpa_layar:
            buka_layar(a.port)
        return 0

    h = logging.handlers.RotatingFileHandler(konfig.jalur("pos.log"), maxBytes=1_000_000, backupCount=3,
                                             encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[h, logging.StreamHandler(sys.stderr)]
                        if sys.stderr else [h],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("presensiku_pos")
    log.info("Presensiku Pos %s mulai, data di %s", VERSI, konfig.folder_data())

    from . import web
    from .mesin import Mesin
    mesin = Mesin()
    web.mulai(mesin, a.port)
    mesin.mulai()

    if os.name == "nt":
        from .masukan_windows import PembacaRawInput
        try:
            PembacaRawInput(mesin.tombol, terima_virtual=a.uji_virtual).mulai()
        except OSError:
            log.exception("Scanner mode keyboard tidak bisa dibaca")
            mesin.peringatan = "Scanner USB mode keyboard tidak bisa dibaca (lihat pos.log)"
    try:
        from .masukan_serial import PembacaSerial
        PembacaSerial(mesin.teks_com).mulai()
    except ImportError:
        log.warning("pyserial tidak tersedia: scanner mode COM tidak dibaca")

    if not a.tanpa_layar:
        buka_layar(a.port)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        mesin.berhenti()
    return 0


if __name__ == "__main__":
    sys.exit(main())
