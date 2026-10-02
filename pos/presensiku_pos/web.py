"""Server web lokal Presensiku Pos (hanya 127.0.0.1): halaman pasang + Layar Gerbang."""
import html
import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import VERSI, konfig
from .klien import GalatJaringan, GalatServer

log = logging.getLogger(__name__)

HALAMAN_PASANG = """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pasang Presensiku Pos</title>
<style>body{font-family:system-ui,Segoe UI,sans-serif;background:#0b1220;color:#f2f4f7;display:grid;place-items:center;
min-height:100vh;margin:0;padding:16px}form{background:#111a2e;border:1px solid #1f2a44;border-radius:16px;padding:28px;
max-width:460px;width:100%}h1{margin:0 0 6px;font-size:1.4rem}p{color:#98a2b3;line-height:1.5}label{display:block;
font-weight:600;margin:16px 0 6px}input{width:100%;box-sizing:border-box;padding:12px;border-radius:10px;border:1px solid #344054;
background:#0b1220;color:#fff;font-size:1rem}button{margin-top:20px;width:100%;padding:14px;border:0;border-radius:10px;
background:#2563eb;color:#fff;font-size:1.05rem;font-weight:700;cursor:pointer}.galat{background:#450a0a;color:#fecaca;
padding:10px 12px;border-radius:10px;margin-top:14px}small{color:#98a2b3}</style></head><body>
<form method="post" action="/pasang"><h1>Pasang Presensiku Pos</h1>
<p>Di aplikasi sekolah: <b>Perangkat Scan → Tambah PC Pos</b>, lalu salin alamat server dan kode pasang ke sini.</p>
<label>Alamat server sekolah</label><input name="server" value="@@SERVER@@" placeholder="presensiku.biz.id/smpn1" required>
<label>Kode pasang</label><input name="kode" placeholder="ABCD-EF23" required autocomplete="off" style="letter-spacing:.1em;text-transform:uppercase">
@@GALAT@@<button>Pasangkan</button><p><small>Presensiku Pos v@@VERSI@@</small></p></form></body></html>"""

HALAMAN_LAYAR = """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Layar Gerbang · Presensiku Pos</title>
<link rel="stylesheet" href="/statis/layar_gerbang.css"></head><body>@@ISI@@
<script>window.LAYAR = { sumber: '/api/umpan', aksi: '/api/petakan', jeda: 700 };</script>
<script src="/statis/layar_gerbang.js"></script></body></html>"""

def isi_halaman(templat, **nilai):
    for k, v in nilai.items():
        templat = templat.replace(f"@@{k.upper()}@@", v)
    return templat


STATIS = {"layar_gerbang.js": "application/javascript; charset=utf-8",
          "layar_gerbang.css": "text/css; charset=utf-8"}


def buat_handler(mesin, port):
    asal_sah = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    host_sah = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = f"PresensikuPos/{VERSI}"

        def log_message(self, fmt, *args):  # noqa: D401 — sunyikan log akses
            log.debug(fmt, *args)

        def _kirim(self, status, isi, jenis="application/json; charset=utf-8", header=None):
            if isinstance(isi, (dict, list)):
                isi = json.dumps(isi)
            if isinstance(isi, str):
                isi = isi.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", jenis)
            self.send_header("Content-Length", str(len(isi)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (header or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(isi)

        def _sah(self):
            # cegah DNS rebinding & permintaan dari situs lain di browser yang sama
            if self.headers.get("Host", "") not in host_sah:
                self._kirim(403, {"ok": False, "pesan": "host"})
                return False
            asal = self.headers.get("Origin")
            if self.command == "POST" and asal and asal not in asal_sah:
                self._kirim(403, {"ok": False, "pesan": "asal"})
                return False
            return True

        def _body(self):
            n = min(int(self.headers.get("Content-Length") or 0), 65536)
            return self.rfile.read(n) if n else b""

        def do_GET(self):  # noqa: N802
            if not self._sah():
                return
            u = urlsplit(self.path)
            if u.path == "/":
                if not mesin.terpasang:
                    return self._kirim(200, isi_halaman(HALAMAN_PASANG, server="", galat="", versi=VERSI),
                                       "text/html; charset=utf-8")
                isi = open(konfig.sumber_statis("_layar_isi.html"), encoding="utf-8").read()
                return self._kirim(200, isi_halaman(HALAMAN_LAYAR, isi=isi), "text/html; charset=utf-8")
            if u.path.startswith("/statis/"):
                nama = u.path.rsplit("/", 1)[-1]
                f = konfig.sumber_statis(nama) if nama in STATIS else None
                if not f:
                    return self._kirim(404, {"ok": False})
                return self._kirim(200, open(f, "rb").read(), STATIS[nama])
            if u.path == "/api/umpan":
                q = parse_qs(u.query)
                sejak = q.get("sejak", [None])[0]
                return self._kirim(200, mesin.umpan(int(sejak) if sejak and sejak.isdigit() else None))
            m = re.fullmatch(r"/foto/(\d+)", u.path)
            if m:
                f = konfig.jalur("foto", f"{m.group(1)}.jpg")
                if os.path.exists(f):
                    return self._kirim(200, open(f, "rb").read(), "image/jpeg",
                                       {"Cache-Control": "max-age=86400"})
                return self._kirim(404, {"ok": False})
            if u.path == "/api/status":
                return self._kirim(200, {"versi": VERSI, "terpasang": mesin.terpasang,
                                         "online": mesin.online, "antrean": mesin.antrean.jumlah_belum(),
                                         "scanner": list(mesin.terlihat.values()),
                                         "server": mesin.pos.get("server")})
            self._kirim(404, {"ok": False})

        def do_POST(self):  # noqa: N802
            if not self._sah():
                return
            u = urlsplit(self.path)
            if u.path == "/pasang":
                f = {k: v[0] for k, v in parse_qs(self._body().decode("utf-8", "ignore")).items()}
                try:
                    mesin.pasang(f.get("server", ""), f.get("kode", ""))
                except (GalatServer, GalatJaringan) as e:
                    pesan = str(e) if isinstance(e, GalatServer) else \
                        "Server tidak bisa dihubungi. Periksa alamat & internet."
                    return self._kirim(400, isi_halaman(
                        HALAMAN_PASANG, server=html.escape(f.get("server", "")), versi=VERSI,
                        galat=f'<div class="galat">{html.escape(pesan)}</div>'),
                        "text/html; charset=utf-8")
                return self._kirim(303, b"", "text/plain", {"Location": "/"})
            if u.path == "/api/petakan":
                try:
                    d = json.loads(self._body() or b"{}")
                except ValueError:
                    return self._kirim(400, {"ok": False, "pesan": "data rusak"})
                gid = d.get("gerbang_id")
                return self._kirim(200, mesin.petakan(str(d.get("kunci") or ""),
                                                      int(gid) if isinstance(gid, int) else None,
                                                      bool(d.get("abaikan"))))
            self._kirim(404, {"ok": False})

    return H


def mulai(mesin, port=konfig.PORT):
    srv = ThreadingHTTPServer(("127.0.0.1", port), buat_handler(mesin, port))
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, name="web", daemon=True)
    t.start()
    return srv
