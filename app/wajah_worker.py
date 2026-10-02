"""Layanan wajah bersama untuk semua sekolah di satu VPS (127.0.0.1 saja).

    python -m app.wajah_worker            # dijalankan systemd: presensi-wajah.service

Model OpenCV (±40 MB) dimuat sekali di sini, bukan di tiap proses sekolah. Layanan ini tidak
menyimpan apa pun: menerima gambar, mengembalikan hasil analisis (termasuk embedding).
Wajib header X-Kunci = PRESENSI_WAJAH_KUNCI.
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .services.wajah import Mesin, TidakTersedia

BATAS = 6 * 1024 * 1024
mesin = Mesin()


class Penangan(BaseHTTPRequestHandler):
    server_version = "presensi-wajah"

    def _json(self, kode, data):
        b = json.dumps(data).encode()
        self.send_response(kode)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path != "/sehat":
            return self._json(404, {"ok": False})
        try:
            mesin._muat()
            return self._json(200, {"ok": True, "pesan": "Layanan wajah bersama aktif"})
        except TidakTersedia as e:
            return self._json(200, {"ok": False, "pesan": str(e)})

    def do_POST(self):
        kunci = os.environ.get("PRESENSI_WAJAH_KUNCI", "")
        if not kunci or not hmac.compare_digest(self.headers.get("X-Kunci", ""), kunci):
            return self._json(403, {"ok": False, "pesan": "kunci salah"})
        if self.path != "/analisis":
            return self._json(404, {"ok": False})
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 < n <= BATAS:
            return self._json(413, {"ok": False, "pesan": "gambar terlalu besar"})
        try:
            return self._json(200, mesin.analisis(self.rfile.read(n)))
        except TidakTersedia as e:
            return self._json(503, {"ok": False, "pesan": str(e)})

    def log_message(self, *a):        # jangan tulis log per permintaan (privasi + hemat disk)
        pass


def main():
    port = int(os.environ.get("PRESENSI_WAJAH_PORT", "7100"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Penangan)
    print(f"presensi-wajah di 127.0.0.1:{port}, model: {mesin.folder}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
