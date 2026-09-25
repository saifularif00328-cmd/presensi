"""Presensi Siswa Digital — aplikasi absensi sekolah berbasis QR code."""
import os
import secrets
from datetime import timedelta

from flask import Flask, g, render_template, send_from_directory, url_for
from markupsafe import Markup, escape

from . import config
from .db import close_db, get_setting, init_db


def _secret_key():
    """Secret key sesi, dibuat sekali dan disimpan di folder data."""
    path = os.path.join(config.DATA_DIR, "flask.key")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def create_app(test_config=None, start_jobs=True):
    config.ensure_dirs()
    app = Flask(__name__, template_folder=os.path.join(config.BUNDLE_DIR, "templates"),
                static_folder=os.path.join(config.BUNDLE_DIR, "static"))
    app.config.update(
        SECRET_KEY=_secret_key(),
        DB_PATH=config.DB_PATH,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    init_db(app.config["DB_PATH"])
    app.teardown_appcontext(close_db)

    from . import auth
    from .blueprints import (ibadah, kedisiplinan, main, master_data, notifikasi, perizinan,
                             presensi, sistem)
    from .menu import build_menu
    from .license import TIER_LABEL, current_tier, has_feature
    from . import utils

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(master_data.bp)
    app.register_blueprint(presensi.bp)
    app.register_blueprint(perizinan.bp)
    app.register_blueprint(ibadah.bp)
    app.register_blueprint(kedisiplinan.bp)
    app.register_blueprint(sistem.bp)
    app.register_blueprint(notifikasi.bp)

    app.before_request(auth.load_user)
    if not app.config.get("WTF_CSRF_DISABLED"):
        app.before_request(auth.csrf_protect)

    @app.context_processor
    def inject():
        tier = current_tier()
        return {
            "APP_NAME": config.APP_NAME,
            "APP_VERSION": config.APP_VERSION,
            "nama_sekolah": get_setting("nama_sekolah"),
            "tier": tier,
            "tier_label": TIER_LABEL[tier],
            "has_feature": has_feature,
            "can": auth.can,
            "csrf_token": auth.csrf_token,
            "ROLES": auth.ROLES,
            "menu": build_menu,
            "KET": utils.KETERANGAN,
            "tanggal_indo": utils.tanggal_indo,
            "today": utils.today_str,
            "ibadah_aktif": lambda: get_setting("modul_ibadah_aktif") == "1",
        }

    def icon(name, cls=""):
        """Ikon SVG (Lucide) dari sprite lokal — tetap tampil saat offline."""
        href = url_for("static", filename="icons.svg") + "#" + str(escape(name))
        return Markup(f'<svg class="ico {escape(cls)}" aria-hidden="true"><use href="{href}"/></svg>')

    app.jinja_env.globals["icon"] = icon

    @app.template_filter("jam")
    def fmt_jam(v):
        return v[:5] if v else "-"

    @app.route("/uploads/<path:filename>")
    def uploads(filename):
        if g.user is None:
            return "", 403
        return send_from_directory(config.UPLOAD_DIR, filename)

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", kode=403,
                               pesan="Anda tidak memiliki akses ke halaman ini."), 403

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("error.html", kode=400, pesan=e.description), 400

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", kode=404, pesan="Halaman tidak ditemukan."), 404

    if start_jobs and not app.config.get("TESTING"):
        from .scheduler import start
        start(app)

    return app
