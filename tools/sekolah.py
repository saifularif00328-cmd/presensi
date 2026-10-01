#!/opt/presensi/venv/bin/python
"""Kelola sekolah di server VPS (khusus vendor, jalankan sebagai root lewat SSH).

    presensi-sekolah tambah smpn1 --nama "SMP Negeri 1 Contoh" --hari 365 [--maks-siswa 1000]
                                  [--zona Asia/Makassar] [--uji-coba]
    presensi-sekolah daftar
    presensi-sekolah perpanjang smpn1 --hari 180          (atau --sampai 2027-06-30)
    presensi-sekolah nonaktif smpn1 / aktifkan smpn1        (langganan: baca-saja / aktif)
    presensi-sekolah pindah smpn1 backup.zip [--nama ...]   (dari server sekolah -> VPS)
    presensi-sekolah backup smpn1 | --semua
    presensi-sekolah hapus smpn1 --ya
    presensi-sekolah status                                 (RAM, disk, layanan)

Setiap sekolah = database MySQL sendiri + folder /srv/presensi/<kode> + layanan
presensi@<kode> + satu blok Nginx (https://<domain>/<kode>/ -> port).
"""
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))
sys.path.insert(0, APP_DIR)

ROOT = os.environ.get("PRESENSI_SRV", "/srv/presensi")
DOMAIN = os.environ.get("PRESENSI_DOMAIN", "presensiku.biz.id")
NGINX_CONF = os.environ.get("PRESENSI_NGINX_CONF", "/etc/nginx/presensi-sekolah.conf")
PORT_AWAL = 7001
TANPA_SISTEM = os.environ.get("PRESENSI_TANPA_SISTEM") == "1"  # uji: tanpa systemctl/nginx/chown


def _registry_path():
    return os.path.join(ROOT, "sekolah.json")


def muat():
    try:
        with open(_registry_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def simpan(reg):
    os.makedirs(ROOT, exist_ok=True)
    tmp = _registry_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _registry_path())


def sh(*cmd, cek=True):
    if TANPA_SISTEM:
        return ""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if cek and r.returncode != 0:
        raise SystemExit(f"Gagal: {' '.join(cmd)}\n{r.stderr or r.stdout}")
    return r.stdout


def _admin_db():
    """Koneksi MySQL sebagai admin (root lewat socket di VPS, atau env PRESENSI_ADMIN_DB_URL)."""
    import pymysql
    url = os.environ.get("PRESENSI_ADMIN_DB_URL")
    if url:
        from urllib.parse import unquote, urlparse
        u = urlparse(url)
        return pymysql.connect(host=u.hostname, port=u.port or 3306,
                               user=unquote(u.username or "root"),
                               password=unquote(u.password or ""), autocommit=True)
    return pymysql.connect(unix_socket="/run/mysqld/mysqld.sock", user="root", autocommit=True)


def _db_url(s):
    host = os.environ.get("PRESENSI_APP_DB_HOST", "127.0.0.1")
    return f"mysql://{s['db_user']}:{s['db_pass']}@{host}:3306/{s['db']}"


def _dir(kode):
    return os.path.join(ROOT, kode)


def _tulis_env(kode, s):
    d = _dir(kode)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "env"), "w", encoding="utf-8") as f:
        f.write(f"PRESENSI_MODE=cloud\nPRESENSI_HOST=127.0.0.1\nPRESENSI_PORT={s['port']}\n"
                f"PRESENSI_DATA_DIR={d}/data\nPRESENSI_DB_URL={_db_url(s)}\n"
                f"PRESENSI_THREADS={os.environ.get('PRESENSI_THREADS', '4')}\n")
    os.chmod(os.path.join(d, "env"), 0o600)


def _tulis_vendor(kode, s):
    """Status langganan yang dibaca aplikasi (app/license.py, mode cloud)."""
    d = os.path.join(_dir(kode), "data")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_vendor.json"), "w", encoding="utf-8") as f:
        json.dump({"status": s["status"], "berlaku_sampai": s["sampai"],
                   "maks_siswa": s["maks_siswa"], "sekolah": s["nama"]}, f, indent=1)


def blok_nginx(kode, port):
    """Blok Nginx satu sekolah: /<kode>/... diteruskan ke layanan sekolah dengan prefix jalur."""
    return (f"location = /{kode} {{ return 301 /{kode}/; }}\n"
            f"location /{kode}/ {{\n"
            f"    proxy_pass http://127.0.0.1:{port}/;\n"
            "    proxy_http_version 1.1;\n"
            "    proxy_set_header Host $host;\n"
            "    proxy_set_header X-Forwarded-Host $host;\n"
            "    proxy_set_header X-Forwarded-Proto https;\n"
            f"    proxy_set_header X-Forwarded-Prefix /{kode};\n"
            "    proxy_set_header X-Forwarded-For $http_cf_connecting_ip;\n"
            "    proxy_set_header CF-Connecting-IP $http_cf_connecting_ip;\n"
            "    proxy_read_timeout 120s;\n"
            "}\n")


def _tulis_map(reg):
    os.makedirs(os.path.dirname(NGINX_CONF) or ".", exist_ok=True)
    with open(NGINX_CONF, "w", encoding="utf-8") as f:
        f.write("# Dikelola otomatis oleh presensi-sekolah — jangan diedit manual\n")
        for kode, s in sorted(reg.items()):
            f.write(blok_nginx(kode, s["port"]))
    sh("nginx", "-t")
    sh("systemctl", "reload", "nginx")


def _chown(kode):
    if not TANPA_SISTEM:
        sh("chown", "-R", "presensi:presensi", _dir(kode))
        os.chmod(os.path.join(_dir(kode), "env"), 0o600)


def _env_sekolah(kode, s):
    env = dict(os.environ)
    env.update(PRESENSI_MODE="cloud", PRESENSI_DATA_DIR=os.path.join(_dir(kode), "data"),
               PRESENSI_DB_URL=_db_url(s))
    return env


def _jalankan_di_sekolah(kode, s, kode_python):
    """Jalankan potongan Python dengan konfigurasi sekolah (database & folder data sendiri)."""
    r = subprocess.run([sys.executable, "-c", kode_python], cwd=APP_DIR,
                       env=_env_sekolah(kode, s), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stderr[-2000:])
    return r.stdout


def _validasi_kode(kode):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", kode or ""):
        raise SystemExit("Kode sekolah hanya huruf kecil/angka/tanda minus, mis. smpn1")


# ------------------------------------------------------------------ perintah
def tambah(a, reg=None):
    _validasi_kode(a.kode)
    reg = reg if reg is not None else muat()
    if a.kode in reg:
        raise SystemExit(f"Sekolah {a.kode} sudah ada.")
    dipakai = {s["port"] for s in reg.values()}
    port = next(p for p in range(PORT_AWAL, PORT_AWAL + 1000) if p not in dipakai)
    sampai = a.sampai or (date.today() + timedelta(days=a.hari)).isoformat()
    s = {"nama": a.nama, "port": port, "db": f"presensi_{a.kode.replace('-', '_')}",
         "db_user": f"p_{a.kode.replace('-', '_')}"[:32], "db_pass": secrets.token_urlsafe(18),
         "status": "uji_coba" if a.uji_coba else "aktif", "sampai": sampai,
         "maks_siswa": a.maks_siswa, "zona": a.zona, "dibuat": date.today().isoformat()}
    conn = _admin_db()
    with conn.cursor() as c:
        c.execute(f"CREATE DATABASE IF NOT EXISTS `{s['db']}` CHARACTER SET utf8mb4 "
                  "COLLATE utf8mb4_unicode_ci")
        host = os.environ.get("PRESENSI_APP_DB_USER_HOST", "localhost")
        c.execute(f"CREATE USER IF NOT EXISTS '{s['db_user']}'@'{host}' IDENTIFIED BY %s",
                  (s["db_pass"],))
        c.execute(f"ALTER USER '{s['db_user']}'@'{host}' IDENTIFIED BY %s", (s["db_pass"],))
        c.execute(f"GRANT ALL PRIVILEGES ON `{s['db']}`.* TO '{s['db_user']}'@'{host}'")
    conn.close()
    _tulis_env(a.kode, s)
    _tulis_vendor(a.kode, s)
    # buat tabel + isi awal, set nama sekolah & zona waktu
    _jalankan_di_sekolah(a.kode, s, (
        "from app.db import init_db, connect, set_setting\n"
        "from app import config\n"
        "init_db(config.database())\n"
        "db = connect(config.database())\n"
        f"set_setting('nama_sekolah', {a.nama!r}, db=db)\n"
        f"set_setting('zona_waktu', {a.zona!r}, db=db)\n"
        f"set_setting('alamat_publik', 'https://{DOMAIN}/{a.kode}', db=db)\n"
        "db.close()\n"))
    reg[a.kode] = s
    simpan(reg)
    _chown(a.kode)
    sh("systemctl", "enable", "--now", f"presensi@{a.kode}")
    _tulis_map(reg)
    print(f"Sekolah {a.kode} dibuat: https://{DOMAIN}/{a.kode}  (port {port})")
    print(f"Langganan: {s['status']} sampai {sampai}; login awal admin / admin123 (wajib diganti).")
    return s


def daftar(_a):
    reg = muat()
    if not reg:
        print("Belum ada sekolah.")
        return
    print(f"{'KODE':<14}{'NAMA':<30}{'PORT':<6}{'STATUS':<10}{'SAMPAI':<12}LAYANAN")
    for kode, s in sorted(reg.items()):
        aktif = sh("systemctl", "is-active", f"presensi@{kode}", cek=False).strip() or "-"
        print(f"{kode:<14}{s['nama'][:28]:<30}{s['port']:<6}{s['status']:<10}{s['sampai'] or '-':<12}"
              f"{aktif}")


def _ubah(kode, **perubahan):
    reg = muat()
    if kode not in reg:
        raise SystemExit(f"Sekolah {kode} tidak ada.")
    reg[kode].update(perubahan)
    simpan(reg)
    _tulis_vendor(kode, reg[kode])
    _chown(kode)
    return reg[kode]


def perpanjang(a):
    reg = muat()
    if a.kode not in reg:
        raise SystemExit(f"Sekolah {a.kode} tidak ada.")
    if a.sampai:
        sampai = a.sampai
    else:
        dasar = max(date.today(), datetime.strptime(reg[a.kode]["sampai"], "%Y-%m-%d").date()) \
            if reg[a.kode].get("sampai") else date.today()
        sampai = (dasar + timedelta(days=a.hari)).isoformat()   # menyambung dari tanggal habis
    s = _ubah(a.kode, sampai=sampai, status="aktif",
              maks_siswa=a.maks_siswa if a.maks_siswa is not None else reg[a.kode]["maks_siswa"])
    print(f"{a.kode}: aktif sampai {s['sampai']}")


def nonaktif(a):
    _ubah(a.kode, status="nonaktif")
    print(f"{a.kode}: dinonaktifkan (mode baca-saja).")


def aktifkan(a):
    _ubah(a.kode, status="aktif")
    print(f"{a.kode}: aktif kembali.")


def backup(a):
    reg = muat()
    kodes = sorted(reg) if a.semua else [a.kode]
    tujuan = os.path.join(ROOT, "_backup")
    os.makedirs(tujuan, exist_ok=True)
    for kode in kodes:
        if kode not in reg:
            raise SystemExit(f"Sekolah {kode} tidak ada.")
        out = os.path.join(tujuan, f"{kode}-{date.today().isoformat()}.zip")
        _jalankan_di_sekolah(kode, reg[kode], (
            "from app.db import connect\nfrom app import config\n"
            "from app.services.backup import make_zip\n"
            "db = connect(config.database())\n"
            f"open({out!r}, 'wb').write(make_zip(db))\ndb.close()\n"))
        lama = sorted(f for f in os.listdir(tujuan) if f.startswith(kode + "-"))
        for f in lama[:-14]:
            os.remove(os.path.join(tujuan, f))
        print(f"{kode}: {out}")


def pindah(a):
    """Impor backup ZIP dari server sekolah ke VPS (sekolah dibuat bila belum ada)."""
    if not os.path.exists(a.zip):
        raise SystemExit(f"File tidak ada: {a.zip}")
    reg = muat()
    if a.kode not in reg:
        a.nama = a.nama or a.kode.upper()
        tambah(a, reg)
        reg = muat()
    s = reg[a.kode]
    sh("systemctl", "stop", f"presensi@{a.kode}", cek=False)
    meta = _jalankan_di_sekolah(a.kode, s, (
        "import json\nfrom app import config\nfrom app.db import connect, init_db, set_setting\n"
        "from app.services.backup import restore_zip\n"
        f"meta = restore_zip(open({a.zip!r}, 'rb').read(), config.database(), config.DATA_DIR)\n"
        "init_db(config.database())  # sesuaikan skema bila backup dari versi lama\n"
        "db = connect(config.database())\n"
        f"set_setting('alamat_publik', 'https://{DOMAIN}/{a.kode}', db=db)\n"
        "db.close()\nprint(json.dumps(meta))\n"))
    _tulis_vendor(a.kode, s)   # langganan tetap diatur vendor (bukan dari backup)
    _chown(a.kode)
    sh("systemctl", "start", f"presensi@{a.kode}")
    print(f"{a.kode}: data dipulihkan dari {a.zip} ({meta.strip()})")
    print(f"Alamat sekolah: https://{DOMAIN}/{a.kode}")


def hapus(a):
    if not a.ya:
        raise SystemExit("Tambahkan --ya untuk benar-benar menghapus (backup dibuat dulu).")
    reg = muat()
    if a.kode not in reg:
        raise SystemExit(f"Sekolah {a.kode} tidak ada.")
    a.semua = False
    backup(a)
    s = reg.pop(a.kode)
    sh("systemctl", "disable", "--now", f"presensi@{a.kode}", cek=False)
    conn = _admin_db()
    with conn.cursor() as c:
        c.execute(f"DROP DATABASE IF EXISTS `{s['db']}`")
        host = os.environ.get("PRESENSI_APP_DB_USER_HOST", "localhost")
        c.execute(f"DROP USER IF EXISTS '{s['db_user']}'@'{host}'")
    conn.close()
    shutil.rmtree(_dir(a.kode), ignore_errors=True)
    simpan(reg)
    _tulis_map(reg)
    print(f"{a.kode} dihapus (backup terakhir di {ROOT}/_backup).")


def status(_a):
    print(sh("free", "-h", cek=False))
    print(sh("df", "-h", ROOT, cek=False))
    daftar(_a)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tambah")
    p.add_argument("kode")
    p.add_argument("--nama", required=True)
    p.add_argument("--hari", type=int, default=365)
    p.add_argument("--sampai")
    p.add_argument("--maks-siswa", type=int, default=0)
    p.add_argument("--zona", default="Asia/Jakarta",
                   choices=["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"])
    p.add_argument("--uji-coba", action="store_true")
    p.set_defaults(fn=tambah)
    sub.add_parser("daftar").set_defaults(fn=daftar)
    p = sub.add_parser("perpanjang")
    p.add_argument("kode")
    p.add_argument("--hari", type=int, default=365)
    p.add_argument("--sampai")
    p.add_argument("--maks-siswa", type=int)
    p.set_defaults(fn=perpanjang)
    for nama, fn in (("nonaktif", nonaktif), ("aktifkan", aktifkan)):
        p = sub.add_parser(nama)
        p.add_argument("kode")
        p.set_defaults(fn=fn)
    p = sub.add_parser("backup")
    p.add_argument("kode", nargs="?")
    p.add_argument("--semua", action="store_true")
    p.set_defaults(fn=backup)
    p = sub.add_parser("pindah")
    p.add_argument("kode")
    p.add_argument("zip")
    p.add_argument("--nama")
    p.add_argument("--hari", type=int, default=365)
    p.add_argument("--sampai")
    p.add_argument("--maks-siswa", type=int, default=0)
    p.add_argument("--zona", default="Asia/Jakarta")
    p.add_argument("--uji-coba", action="store_true")
    p.set_defaults(fn=pindah)
    p = sub.add_parser("hapus")
    p.add_argument("kode")
    p.add_argument("--ya", action="store_true")
    p.set_defaults(fn=hapus)
    sub.add_parser("status").set_defaults(fn=status)
    a = ap.parse_args(argv)
    if a.cmd == "backup" and not a.semua and not a.kode:
        ap.error("sebutkan kode sekolah atau --semua")
    return a.fn(a)


if __name__ == "__main__":
    main()
