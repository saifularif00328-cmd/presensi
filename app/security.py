"""Pengamanan saat aplikasi dibuka dari internet (Cloudflare Tunnel / Nginx di VPS).

- IP & skema asli dibaca dari header proxy HANYA bila permintaan datang dari proxy lokal
  (cloudflared / Nginx di mesin yang sama), sehingga klien LAN tidak bisa memalsukannya.
- Cookie sesi diberi flag Secure otomatis bila diakses lewat HTTPS (akses LAN http tetap jalan).
- Header keamanan dasar di setiap respons.
- Pembatasan percobaan login (per akun & per IP) dengan kunci sementara.
"""
import re
from datetime import timedelta
from ipaddress import ip_address

from flask import request
from flask.sessions import SecureCookieSessionInterface

from . import utils
from .db import execute, query

PROXY_LOKAL = {"127.0.0.1", "::1"}
PREFIX_VALID = re.compile(r"^/[a-z0-9][a-z0-9-]{0,40}$")

MAKS_GAGAL_AKUN = 5          # salah password berturut-turut per akun
MAKS_GAGAL_IP = 20           # per alamat IP
KUNCI_MENIT = 15


class ProxyLokal:
    """Middleware WSGI: pakai CF-Connecting-IP / X-Forwarded-* dari proxy lokal saja."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("REMOTE_ADDR") in PROXY_LOKAL:
            ip = (environ.get("HTTP_CF_CONNECTING_IP")
                  or (environ.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip())
            if ip:
                try:
                    ip_address(ip)
                    environ["REMOTE_ADDR"] = ip
                except ValueError:
                    pass
            proto = (environ.get("HTTP_X_FORWARDED_PROTO") or "").split(",")[0].strip()
            if proto in ("http", "https"):
                environ["wsgi.url_scheme"] = proto
            host = environ.get("HTTP_X_FORWARDED_HOST")
            if host:
                environ["HTTP_HOST"] = host.split(",")[0].strip()
            # Aplikasi dibuka di bawah jalur, mis. https://presensiku.biz.id/smpn1 (Nginx VPS)
            prefix = (environ.get("HTTP_X_FORWARDED_PREFIX") or "").rstrip("/")
            if PREFIX_VALID.match(prefix):
                environ["SCRIPT_NAME"] = prefix
                path = environ.get("PATH_INFO", "")
                if path == prefix or path.startswith(prefix + "/"):
                    environ["PATH_INFO"] = path[len(prefix):] or "/"
        return self.app(environ, start_response)


class SesiAman(SecureCookieSessionInterface):
    def get_cookie_secure(self, app):
        return request.is_secure or app.config.get("SESSION_COOKIE_SECURE", False)

    def get_cookie_path(self, app):
        # tiap sekolah (/smpn1, /smpn2, ...) punya cookie login sendiri di domain yang sama
        return request.script_root or app.config.get("SESSION_COOKIE_PATH") or "/"


def header_keamanan(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
    if request.is_secure:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
    return resp


# ------------------------------------------------------------------ batas login
def _kunci(jenis, nilai):
    return f"{jenis}:{(nilai or '').lower()[:150]}"


def terkunci(username, ip):
    """Kembalikan menit tersisa bila akun/IP sedang dikunci, else 0."""
    now = utils.now()
    for k in (_kunci("akun", username), _kunci("ip", ip)):
        r = query("SELECT terkunci_sampai FROM login_gagal WHERE kunci = ?", (k,), one=True)
        if r and r["terkunci_sampai"]:
            sampai = utils.parse_datetime(r["terkunci_sampai"])
            if sampai and sampai > now:
                return max(1, int((sampai - now).total_seconds() // 60) + 1)
    return 0


def catat_gagal(username, ip):
    now = utils.now()
    for k, maks in ((_kunci("akun", username), MAKS_GAGAL_AKUN), (_kunci("ip", ip), MAKS_GAGAL_IP)):
        r = query("SELECT * FROM login_gagal WHERE kunci = ?", (k,), one=True)
        pertama = utils.parse_datetime(r["pertama"]) if r else None
        if r is None or (pertama and now - pertama > timedelta(minutes=KUNCI_MENIT)):
            jumlah, pertama = 1, now
        else:
            jumlah = r["jumlah"] + 1
        sampai = now + timedelta(minutes=KUNCI_MENIT) if jumlah >= maks else None
        execute("INSERT INTO login_gagal(kunci, jumlah, pertama, terkunci_sampai) "
                "VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE jumlah = VALUES(jumlah), "
                "pertama = VALUES(pertama), terkunci_sampai = VALUES(terkunci_sampai)",
                (k, jumlah, pertama.strftime("%Y-%m-%d %H:%M:%S"),
                 sampai.strftime("%Y-%m-%d %H:%M:%S") if sampai else None))


def reset_gagal(username):
    execute("DELETE FROM login_gagal WHERE kunci = ?", (_kunci("akun", username),))
