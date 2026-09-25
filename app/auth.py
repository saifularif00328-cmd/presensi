"""Login, role, dan pembatasan fitur per tier lisensi."""
import hmac
import secrets
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

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


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


def csrf_protect():
    """Tolak POST tanpa token CSRF yang valid (form field `_csrf` atau header)."""
    if request.method != "POST" or request.endpoint == "static":
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
        user = query("SELECT * FROM users WHERE username = ? AND aktif = 1",
                     (request.form.get("username", "").strip(),), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
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
        flash("Username atau password salah.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
