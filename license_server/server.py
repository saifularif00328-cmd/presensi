"""Server Aktivasi Lisensi — Presensi Siswa Digital (dijalankan di laptop/server vendor).

    python license_server/server.py            → http://localhost:8500

- Halaman admin: buat lisensi + kode aktivasi, ubah masa berlaku/tier, cabut, reset perangkat,
  buat kode lisensi offline.
- API untuk aplikasi sekolah: POST /api/activate, POST /api/check.
- Agar bisa diakses sekolah lewat internet, gunakan Cloudflare Tunnel / ngrok
  (lihat license_server/README.md).

Butuh kunci privat vendor: python tools/vendor_init.py
"""
import hmac
import os
import secrets
import sqlite3
import sys
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,  # noqa: E402
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402

from app.license import (TIER_LABEL, TIERS, load_private_key, make_license,  # noqa: E402
                         sign_status)

DATA_DIR = os.environ.get("LISENSI_DATA_DIR", os.path.join(HERE, "data"))
DB_PATH = os.path.join(DATA_DIR, "lisensi.db")
KEY_PATH = os.environ.get("LISENSI_PRIVATE_KEY", os.path.join(ROOT, "vendor", "private_key.pem"))
KODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # tanpa 0/O/1/I agar tidak tertukar

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lid TEXT NOT NULL UNIQUE,
    kode TEXT NOT NULL UNIQUE,
    sekolah TEXT NOT NULL,
    kontak TEXT,
    tier TEXT NOT NULL,
    exp TEXT,                                  -- NULL = selamanya
    max_device INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'aktif',      -- aktif / dicabut
    catatan TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id INTEGER NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
    device TEXT NOT NULL,
    aktif INTEGER NOT NULL DEFAULT 1,
    sekolah_app TEXT,
    app_version TEXT,
    ip TEXT,
    first_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_seen TEXT,
    UNIQUE (license_id, device)
);
"""


def create_app(test_config=None):
    app = Flask(__name__, template_folder=os.path.join(HERE, "templates"),
                static_folder=os.path.join(ROOT, "app", "static"))  # pakai CSS/ikon aplikasi
    os.makedirs(DATA_DIR, exist_ok=True)
    key_file = os.path.join(DATA_DIR, "flask.key")
    if not os.path.exists(key_file):
        with open(key_file, "w") as f:
            f.write(secrets.token_hex(32))
    app.config.update(SECRET_KEY=open(key_file).read().strip(), DB_PATH=DB_PATH,
                      KEY_PATH=KEY_PATH, SESSION_COOKIE_SAMESITE="Lax")
    if test_config:
        app.config.update(test_config)
    with sqlite3.connect(app.config["DB_PATH"]) as c:
        c.executescript(SCHEMA)

    # ------------------------------------------------------------ helper
    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close(_e):
        d = g.pop("db", None)
        if d is not None:
            d.close()

    def setting(key, value=None):
        if value is None:
            r = db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return r["value"] if r else None
        db().execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) "
                     "DO UPDATE SET value = excluded.value", (key, value))
        db().commit()

    _priv = {}

    def private_key():
        path = app.config["KEY_PATH"]
        if path not in _priv:
            _priv[path] = load_private_key(path) if os.path.exists(path) else None
        return _priv[path]

    def new_kode():
        while True:
            raw = "".join(secrets.choice(KODE_CHARS) for _ in range(12))
            kode = f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"
            if not db().execute("SELECT 1 FROM licenses WHERE kode = ?", (kode,)).fetchone():
                return kode

    def expired(lic):
        return bool(lic["exp"]) and lic["exp"] < date.today().isoformat()

    def issue(lic, device):
        return make_license(private_key(), device, lic["tier"], lic["sekolah"], lic["exp"],
                            lic["lid"])

    app.jinja_env.globals.update(TIER_LABEL=TIER_LABEL, TIERS=TIERS, today=lambda: date.today().isoformat())

    # ------------------------------------------------------------ auth admin + CSRF
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(24)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    def icon(name, cls=""):
        from markupsafe import Markup, escape
        href = url_for("static", filename="icons.svg") + "#" + str(escape(name))
        return Markup(f'<svg class="ico {escape(cls)}" aria-hidden="true"><use href="{href}"/></svg>')

    app.jinja_env.globals["icon"] = icon

    @app.before_request
    def guard():
        if request.path.startswith("/api/") or request.endpoint in ("static", "favicon", None):
            return None
        if request.method == "POST":
            sent = request.form.get("_csrf", "")
            if not session.get("_csrf") or not hmac.compare_digest(sent, session["_csrf"]):
                abort(400)
        if setting("admin_password") is None and request.endpoint != "setup":
            return redirect(url_for("setup"))
        if request.endpoint not in ("login", "setup") and not session.get("admin"):
            return redirect(url_for("login"))
        return None

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if setting("admin_password") is not None:
            return redirect(url_for("login"))
        if request.method == "POST":
            pw = request.form.get("password", "")
            if len(pw) < 8 or pw != request.form.get("ulang"):
                flash("Password minimal 8 karakter dan harus sama.", "error")
            else:
                setting("admin_password", generate_password_hash(pw))
                session["admin"] = True
                return redirect(url_for("index"))
        return render_template("setup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if check_password_hash(setting("admin_password") or "", request.form.get("password", "")):
                session.clear()
                session["admin"] = True
                return redirect(url_for("index"))
            flash("Password salah.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ------------------------------------------------------------ admin
    @app.route("/")
    def index():
        q = request.args.get("q", "").strip()
        sql = ("SELECT l.*, (SELECT COUNT(*) FROM activations a WHERE a.license_id = l.id AND "
               "a.aktif = 1) AS n_dev, (SELECT MAX(last_seen) FROM activations a WHERE "
               "a.license_id = l.id) AS last_seen FROM licenses l")
        args = []
        if q:
            sql += " WHERE l.sekolah LIKE ? OR l.kode LIKE ? OR l.lid LIKE ?"
            args = [f"%{q}%"] * 3
        rows = db().execute(sql + " ORDER BY l.id DESC", args).fetchall()
        stats = {
            "total": len(rows), "aktif": sum(1 for r in rows if r["status"] == "aktif" and not expired(r)),
            "segera": sum(1 for r in rows if r["exp"] and r["status"] == "aktif" and not expired(r)
                          and r["exp"] <= (date.today() + timedelta(days=30)).isoformat()),
            "dicabut": sum(1 for r in rows if r["status"] == "dicabut"),
        }
        return render_template("index.html", rows=rows, stats=stats, q=q,
                               key_ok=private_key() is not None, expired=expired)

    @app.route("/lisensi/baru", methods=["POST"])
    def baru():
        sekolah = request.form.get("sekolah", "").strip()
        tier = request.form.get("tier")
        if not sekolah or tier not in TIERS:
            flash("Nama sekolah dan tier wajib diisi.", "error")
            return redirect(url_for("index"))
        durasi = request.form.get("durasi", "365")
        exp = None if durasi == "0" else (date.today() + timedelta(days=int(durasi))).isoformat()
        if request.form.get("exp"):
            exp = request.form["exp"]
        cur = db().execute(
            "INSERT INTO licenses(lid, kode, sekolah, kontak, tier, exp, max_device, catatan) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (secrets.token_hex(6).upper(), new_kode(), sekolah, request.form.get("kontak", "").strip(),
             tier, exp, max(int(request.form.get("max_device") or 1), 1),
             request.form.get("catatan", "").strip()))
        db().commit()
        flash("Lisensi dibuat. Kirim kode aktivasi ke sekolah.", "success")
        return redirect(url_for("detail", lid=cur.lastrowid))

    @app.route("/lisensi/<int:lid>", methods=["GET", "POST"])
    def detail(lid):
        lic = db().execute("SELECT * FROM licenses WHERE id = ?", (lid,)).fetchone() or abort(404)
        offline_key = None
        if request.method == "POST":
            aksi = request.form.get("aksi")
            if aksi == "simpan":
                tier = request.form.get("tier")
                exp = request.form.get("exp") or None
                if tier in TIERS:
                    db().execute("UPDATE licenses SET sekolah = ?, kontak = ?, tier = ?, exp = ?, "
                                 "max_device = ?, catatan = ? WHERE id = ?",
                                 (request.form.get("sekolah", lic["sekolah"]).strip(),
                                  request.form.get("kontak", "").strip(), tier, exp,
                                  max(int(request.form.get("max_device") or 1), 1),
                                  request.form.get("catatan", "").strip(), lid))
                    db().commit()
                    flash("Disimpan. Sekolah menerima perubahan otomatis saat aplikasinya online.",
                          "success")
            elif aksi in ("cabut", "pulihkan"):
                db().execute("UPDATE licenses SET status = ? WHERE id = ?",
                             ("dicabut" if aksi == "cabut" else "aktif", lid))
                db().commit()
                flash("Lisensi dicabut." if aksi == "cabut" else "Lisensi dipulihkan.", "success")
            elif aksi == "reset":
                db().execute("UPDATE activations SET aktif = 0 WHERE id = ? AND license_id = ?",
                             (int(request.form.get("act_id", 0)), lid))
                db().commit()
                flash("Perangkat dilepas. Kode aktivasi bisa dipakai di perangkat baru.", "success")
            elif aksi == "hapus":
                db().execute("DELETE FROM licenses WHERE id = ?", (lid,))
                db().commit()
                flash("Lisensi dihapus.", "success")
                return redirect(url_for("index"))
            elif aksi == "offline":
                dev = request.form.get("device", "").strip().upper()
                if not dev or private_key() is None:
                    flash("Isi ID perangkat (dan pastikan kunci privat tersedia).", "error")
                else:
                    offline_key = issue(lic, dev)
                    db().execute("INSERT INTO activations(license_id, device, sekolah_app, last_seen) "
                                 "VALUES (?,?,?,?) ON CONFLICT(license_id, device) DO UPDATE SET "
                                 "aktif = 1", (lid, dev, "(offline)", None))
                    db().commit()
            if aksi != "offline":
                return redirect(url_for("detail", lid=lid))
            lic = db().execute("SELECT * FROM licenses WHERE id = ?", (lid,)).fetchone()
        acts = db().execute("SELECT * FROM activations WHERE license_id = ? ORDER BY aktif DESC, "
                            "id DESC", (lid,)).fetchall()
        return render_template("detail.html", lic=lic, acts=acts, offline_key=offline_key,
                               expired=expired(lic), key_ok=private_key() is not None)

    # ------------------------------------------------------------ API
    hits = defaultdict(deque)

    def limited(limit=20, window=60):
        ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"
        now = time.time()
        q = hits[ip]
        while q and q[0] < now - window:
            q.popleft()
        q.append(now)
        return len(q) > limit

    @app.route("/api/activate", methods=["POST"])
    def api_activate():
        if limited():
            return jsonify(ok=False, error="Terlalu banyak percobaan. Coba lagi 1 menit lagi."), 429
        if private_key() is None:
            return jsonify(ok=False, error="Server lisensi belum siap (kunci privat tidak ada)."), 503
        d = request.get_json(silent=True) or {}
        kode = str(d.get("code", "")).strip().upper()
        device = str(d.get("device", "")).strip().upper()
        if not kode or not device:
            return jsonify(ok=False, error="Kode aktivasi dan ID perangkat wajib diisi."), 400
        lic = db().execute("SELECT * FROM licenses WHERE kode = ?", (kode,)).fetchone()
        if lic is None:
            return jsonify(ok=False, error="Kode aktivasi tidak dikenal."), 404
        if lic["status"] != "aktif":
            return jsonify(ok=False, error="Lisensi ini telah dicabut. Hubungi vendor."), 403
        if expired(lic):
            return jsonify(ok=False, error=f"Lisensi kedaluwarsa sejak {lic['exp']}."), 403
        act = db().execute("SELECT * FROM activations WHERE license_id = ? AND device = ?",
                           (lic["id"], device)).fetchone()
        if not (act and act["aktif"]):
            n = db().execute("SELECT COUNT(*) FROM activations WHERE license_id = ? AND aktif = 1",
                             (lic["id"],)).fetchone()[0]
            if n >= lic["max_device"]:
                return jsonify(ok=False, error=f"Kode sudah dipakai di {n} perangkat (batas "
                                               f"{lic['max_device']}). Hubungi vendor untuk "
                                               "memindahkan lisensi."), 409
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db().execute("INSERT INTO activations(license_id, device, sekolah_app, app_version, ip, "
                     "last_seen) VALUES (?,?,?,?,?,?) ON CONFLICT(license_id, device) DO UPDATE SET "
                     "aktif = 1, sekolah_app = excluded.sekolah_app, app_version = "
                     "excluded.app_version, ip = excluded.ip, last_seen = excluded.last_seen",
                     (lic["id"], device, str(d.get("sekolah", ""))[:120],
                      str(d.get("app_version", ""))[:20],
                      request.headers.get("CF-Connecting-IP") or request.remote_addr, now))
        db().commit()
        return jsonify(ok=True, license=issue(lic, device),
                       status_token=sign_status(private_key(), lic["lid"], device, "aktif"))

    @app.route("/api/check", methods=["POST"])
    def api_check():
        if limited(60):
            return jsonify(ok=False, error="rate limit"), 429
        if private_key() is None:
            return jsonify(ok=False), 503
        d = request.get_json(silent=True) or {}
        lid = str(d.get("lid", "")).strip().upper()
        device = str(d.get("device", "")).strip().upper()
        lic = db().execute("SELECT * FROM licenses WHERE lid = ?", (lid,)).fetchone()
        if lic is None:
            return jsonify(ok=False, error="unknown"), 404  # lisensi offline di luar server
        act = db().execute("SELECT * FROM activations WHERE license_id = ? AND device = ?",
                           (lic["id"], device)).fetchone()
        aktif = lic["status"] == "aktif" and act is not None and act["aktif"] == 1
        if act is not None:
            db().execute("UPDATE activations SET last_seen = ?, app_version = ? WHERE id = ?",
                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                          str(d.get("app_version", ""))[:20], act["id"]))
            db().commit()
        out = {"ok": True, "status_token": sign_status(private_key(), lic["lid"], device,
                                                       "aktif" if aktif else "dicabut")}
        if aktif:
            out["license"] = issue(lic, device)  # membawa perubahan tier / perpanjangan
        return jsonify(out)

    return app


if __name__ == "__main__":
    host = os.environ.get("LISENSI_HOST", "127.0.0.1")
    port = int(os.environ.get("LISENSI_PORT", "8500"))
    print("=" * 60)
    print(" Server Aktivasi Lisensi — Presensi Siswa Digital")
    print(f"  Admin : http://localhost:{port}")
    if not os.path.exists(KEY_PATH):
        print(f"  PERINGATAN: kunci privat belum ada ({KEY_PATH}).")
        print("  Jalankan dulu: python tools/vendor_init.py")
    print("=" * 60)
    application = create_app()
    try:
        from waitress import serve
        serve(application, host=host, port=port)
    except ImportError:
        application.run(host=host, port=port)
