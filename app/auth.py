"""Login, role, dan pembatasan fitur per tier lisensi."""
import hmac
import secrets
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

from . import security
from .db import query
from .license import FEATURE_LABEL, TIER_LABEL, has_feature, min_tier

bp = Blueprint("auth", __name__)

ROLES = {
    "admin": "Admin / TU",
    "piket": "Guru Piket",
    "bk": "Guru BK / Kedisiplinan",
}


def load_user():
    uid = session.get("user_id")
    g.user = None
    if uid:
        g.user = query("SELECT * FROM users WHERE id = ? AND aktif = 1", (uid,), one=True)


BEBAS_GANTI = {"main.akun", "auth.logout", "static", "uploads", "favicon"}


def wajib_ganti_password():
    """Paksa ganti password awal/sementara sebelum membuka halaman lain."""
    from flask import current_app
    if (g.user is not None and g.user.get("wajib_ganti")
            and current_app.config.get("WAJIB_GANTI_PASSWORD", True)
            and request.endpoint not in BEBAS_GANTI):
        if request.method == "GET":
            flash("Demi keamanan, ganti password Anda terlebih dahulu.", "info")
        return redirect(url_for("main.akun"))
    return None


BEBAS_LANGGANAN = {"auth.login", "auth.logout", "main.akun", "sistem.lisensi", "static"}


def cek_langganan():
    """Langganan habis = mode baca-saja: data tetap bisa dilihat & diekspor, tetapi
    absen dan perubahan data ditolak sampai langganan diperpanjang."""
    if request.method in ("GET", "HEAD", "OPTIONS") or request.endpoint in BEBAS_LANGGANAN:
        return None
    from .license import langganan
    status = langganan()
    if not status["baca_saja"]:
        return None
    pesan = ("Masa langganan telah berakhir — aplikasi dalam mode baca-saja. "
             "Hubungi penyedia untuk memperpanjang.")
    if request.is_json or "/api/" in request.path:
        from flask import jsonify
        return jsonify({"ok": False, "level": "error", "pesan": pesan}), 402
    flash(pesan, "error")
    return redirect(request.referrer or url_for("main.beranda"))


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


# API perangkat memakai tanda tangan HMAC sendiri (bukan sesi browser)
CSRF_BEBAS = {"static", "perangkat.api_ping", "perangkat.api_tap"}


def csrf_protect():
    """Tolak POST tanpa token CSRF yang valid (form field `_csrf` atau header)."""
    if request.method != "POST" or request.endpoint in CSRF_BEBAS:
        return None
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf") or ""
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Token CSRF tidak valid. Muat ulang halaman lalu coba lagi.")
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*a, **kw)
    return wrapped


def roles(*allowed):
    """Batasi akses ke role tertentu. Admin selalu diizinkan."""
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.full_path))
            if g.user["role"] != "admin" and g.user["role"] not in allowed:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


def feature(name):
    """Batasi akses ke fitur sesuai tier lisensi."""
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if not has_feature(name):
                return render_template("locked.html", fitur=FEATURE_LABEL.get(name, name),
                                       tier=TIER_LABEL[min_tier(name)]), 402
            return view(*a, **kw)
        return wrapped
    return deco


def can(*allowed):
    return g.user is not None and (g.user["role"] == "admin" or g.user["role"] in allowed)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        ip = request.remote_addr or ""
        menit = security.terkunci(username, ip)
        if menit:
            flash(f"Terlalu banyak percobaan login gagal. Coba lagi dalam {menit} menit.", "error")
            return render_template("login.html"), 429
        user = query("SELECT * FROM users WHERE username = ? AND aktif = 1", (username,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            security.reset_gagal(username)
            # Tier Basic tanpa multi-user: hanya akun admin yang bisa login
            if user["role"] != "admin" and not has_feature("multiuser"):
                flash("Multi-user hanya tersedia di lisensi Pro/Enterprise.", "error")
                return render_template("login.html"), 402
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            nxt = request.args.get("next") or ""
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("main.beranda")
            return redirect(nxt)
        security.catat_gagal(username, ip)
        flash("Username atau password salah.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
