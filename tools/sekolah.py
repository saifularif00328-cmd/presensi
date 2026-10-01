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
    presensi-sekolah setel --wa 62812xxxx [--hari-demo 7] [--maks-demo 5]  (WA vendor & demo)
    presensi-sekolah proses-antrean                         (pendaftaran demo dari web)
    presensi-sekolah rapikan                                (harian: hentikan demo kedaluwarsa)
    presensi-sekolah info smpn1                             (data pendaftar & langganan)
    presensi-sekolah akun-vendor                            (akun panel https://<domain>/vendor)

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
from daftar import KONFIGURASI_AWAL  # noqa: E402  (wa, nama, hari_demo, maks_demo, henti_setelah)


def konfigurasi():
    try:
        with open(os.path.join(ROOT, "_konfigurasi.json"), encoding="utf-8") as f:
            return {**KONFIGURASI_AWAL, **json.load(f)}
    except (OSError, ValueError):
        return dict(KONFIGURASI_AWAL)


def _rahasia():
    try:
        with open(os.path.join(ROOT, "_rahasia.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _tulis_json(path, data, mode=0o644, milik_presensi=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.chmod(tmp, mode)
    if milik_presensi and not TANPA_SISTEM:
        shutil.chown(tmp, "presensi", "presensi")
    os.replace(tmp, path)


def _demo_aktif(s, today=None):
    today = (today or date.today()).isoformat()
    return s.get("status") == "uji_coba" and (s.get("sampai") or "") >= today


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
        k = konfigurasi()
        json.dump({"status": "nonaktif" if s["status"] == "berhenti" else s["status"],
                   "berlaku_sampai": s["sampai"], "maks_siswa": s["maks_siswa"],
                   "sekolah": s["nama"], "kode": kode, "demo": bool(s.get("pendaftar")),
                   "wa_vendor": k["wa"], "nama_vendor": k["nama"]}, f, indent=1)


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


def blok_nginx_berhenti(kode):
    """Demo yang sudah dihentikan: arahkan ke halaman depan (pesan + tombol WhatsApp)."""
    return (f"location = /{kode} {{ return 302 /?berakhir={kode}; }}\n"
            f"location /{kode}/ {{ return 302 /?berakhir={kode}; }}\n")


def _tulis_publik(reg):
    """Info tanpa rahasia untuk halaman pendaftaran: kode terpakai & jumlah demo aktif."""
    _tulis_json(os.path.join(ROOT, "_publik.json"),
                {"kode": sorted(reg), "demo_aktif": sum(1 for s in reg.values() if _demo_aktif(s))})
    _tulis_ringkasan(reg)


def _statistik(reg):
    """Jumlah siswa aktif & tanggal presensi terakhir per sekolah (lewat akun root MySQL)."""
    out = {}
    try:
        conn = _admin_db()
    except Exception:  # noqa: BLE001
        return out
    with conn.cursor() as c:
        for kode, s in reg.items():
            try:
                c.execute(f"SELECT COUNT(*) FROM `{s['db']}`.siswa WHERE aktif = 1")
                siswa = c.fetchone()[0]
                c.execute(f"SELECT MAX(tanggal) FROM `{s['db']}`.presensi")
                akhir = c.fetchone()[0]
                out[kode] = {"siswa": siswa, "terakhir": akhir.isoformat() if akhir else ""}
            except Exception:  # noqa: BLE001 — database sekolah belum lengkap
                pass
    conn.close()
    return out


def _tulis_ringkasan(reg=None):
    """Data untuk panel vendor (/vendor) — tanpa password database. Hanya root & presensi."""
    reg = muat() if reg is None else reg
    stat = _statistik(reg)
    data = {}
    for kode, s in reg.items():
        d = {k: v for k, v in s.items() if k not in ("db_pass", "db_user", "db")}
        d.update(stat.get(kode, {}))
        d["layanan"] = sh("systemctl", "is-active", f"presensi@{kode}", cek=False).strip() or "-"
        data[kode] = d
    _tulis_json(os.path.join(ROOT, "_ringkasan.json"),
                {"dibuat": datetime.now().isoformat(timespec="seconds"), "sekolah": data},
                mode=0o640, milik_presensi=True)


def _tulis_map(reg):
    os.makedirs(os.path.dirname(NGINX_CONF) or ".", exist_ok=True)
    with open(NGINX_CONF, "w", encoding="utf-8") as f:
        f.write("# Dikelola otomatis oleh presensi-sekolah — jangan diedit manual\n")
        for kode, s in sorted(reg.items()):
            f.write(blok_nginx_berhenti(kode) if s.get("status") == "berhenti"
                    else blok_nginx(kode, s["port"]))
    _tulis_publik(reg)
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
    print(f"{'KODE':<14}{'NAMA':<30}{'PORT':<6}{'STATUS':<10}{'SAMPAI':<12}{'LAYANAN':<10}WA PENDAFTAR")
    for kode, s in sorted(reg.items()):
        aktif = sh("systemctl", "is-active", f"presensi@{kode}", cek=False).strip() or "-"
        print(f"{kode:<14}{s['nama'][:28]:<30}{s['port']:<6}{s['status']:<10}{s['sampai'] or '-':<12}"
              f"{aktif:<10}{(s.get('pendaftar') or {}).get('wa', '')}")


def _ubah(kode, **perubahan):
    reg = muat()
    if kode not in reg:
        raise SystemExit(f"Sekolah {kode} tidak ada.")
    berhenti = reg[kode].get("status") == "berhenti"
    reg[kode].update(perubahan)
    simpan(reg)
    _tulis_vendor(kode, reg[kode])
    _chown(kode)
    if berhenti and reg[kode]["status"] != "berhenti":
        sh("systemctl", "enable", "--now", f"presensi@{kode}")
        _tulis_map(reg)
    elif "status" in perubahan:
        _tulis_publik(reg)
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


def setel(a):
    """Nomor WA vendor (tombol perpanjang di aplikasi & halaman depan) dan aturan demo."""
    k = konfigurasi()
    if a.wa is not None:
        from daftar import normal_wa
        wa = normal_wa(a.wa)
        if not wa:
            raise SystemExit("Nomor WA tidak valid, contoh: 081234567890")
        k["wa"] = wa
    for kunci in ("nama", "hari_demo", "maks_demo", "henti_setelah"):
        if getattr(a, kunci) is not None:
            k[kunci] = getattr(a, kunci)
    _tulis_json(os.path.join(ROOT, "_konfigurasi.json"), k)
    if a.notif_token is not None:
        r = _rahasia()
        r["fonnte_token"] = a.notif_token
        _tulis_json(os.path.join(ROOT, "_rahasia.json"), r, mode=0o600)
    reg = muat()
    for kode, s in reg.items():           # perbarui nomor WA di semua sekolah
        _tulis_vendor(kode, s)
        _chown(kode)
    for kunci, nilai in k.items():
        print(f"{kunci:<14}{nilai}")
    print(f"{'notif WA':<14}{'aktif' if _rahasia().get('fonnte_token') else '-'}")


def _antrean():
    base = os.path.join(ROOT, "_antrean")
    return os.path.join(base, "masuk"), os.path.join(base, "hasil")


def _dir_perintah():
    return os.path.join(ROOT, "_antrean", "perintah")


def _angka(nilai, bawah, atas, bawaan=None):
    try:
        n = int(nilai)
    except (TypeError, ValueError):
        return bawaan
    return n if bawah <= n <= atas else bawaan


def _jalankan_perintah(c):
    """Perintah dari panel vendor (/vendor). Hanya aksi yang terdaftar di sini yang dijalankan."""
    aksi, d = c.get("aksi"), c.get("data") or {}
    if not isinstance(d, dict):
        return {"status": "gagal", "pesan": "Perintah rusak."}
    reg = muat()
    kode = str(d.get("kode") or "")
    if aksi in ("perpanjang", "nonaktif", "aktifkan", "ubah_kontak") and kode not in reg:
        return {"status": "gagal", "pesan": f"Sekolah {kode} tidak ada."}
    if aksi == "perpanjang":
        sampai = str(d.get("sampai") or "")
        if sampai and not re.fullmatch(r"20\d\d-[01]\d-[0-3]\d", sampai):
            return {"status": "gagal", "pesan": "Tanggal tidak valid."}
        hari = _angka(d.get("hari"), 1, 3660)
        if not sampai and not hari:
            return {"status": "gagal", "pesan": "Pilih lama perpanjangan."}
        perpanjang(argparse.Namespace(kode=kode, hari=hari or 0, sampai=sampai or None,
                                      maks_siswa=_angka(d.get("maks_siswa"), 0, 100000)))
        reg = muat()
        reg[kode].setdefault("pembayaran", []).append({
            "tanggal": date.today().isoformat(), "sampai": reg[kode]["sampai"],
            "hari": hari or 0, "nominal": _angka(d.get("nominal"), 0, 10 ** 10, 0),
            "catatan": str(d.get("catatan") or "")[:200]})
        simpan(reg)
        _tulis_ringkasan(reg)
        return {"status": "siap", "kode": kode, "sampai": reg[kode]["sampai"],
                "pesan": f"{reg[kode]['nama']} aktif sampai {reg[kode]['sampai']}."}
    if aksi == "nonaktif":
        nonaktif(argparse.Namespace(kode=kode))
        return {"status": "siap", "kode": kode, "pesan": f"{kode} dinonaktifkan (baca-saja)."}
    if aksi == "aktifkan":
        aktifkan(argparse.Namespace(kode=kode))
        return {"status": "siap", "kode": kode, "pesan": f"{kode} aktif kembali."}
    if aksi == "ubah_kontak":
        from daftar import normal_wa
        pd = reg[kode].setdefault("pendaftar", {})
        if d.get("wa"):
            wa = normal_wa(str(d["wa"]))
            if not wa:
                return {"status": "gagal", "pesan": "Nomor WA tidak valid."}
            pd["wa"] = wa
        for kunci, maks in (("nama", 80), ("jabatan", 60), ("catatan", 500)):
            if kunci in d:
                pd[kunci] = str(d[kunci] or "")[:maks]
        simpan(reg)
        _tulis_ringkasan(reg)
        return {"status": "siap", "kode": kode, "pesan": "Kontak disimpan."}
    if aksi == "setel":
        a = argparse.Namespace(wa=d.get("wa") or None, nama=(str(d.get("nama") or "")[:40] or None),
                               hari_demo=_angka(d.get("hari_demo"), 1, 90),
                               maks_demo=_angka(d.get("maks_demo"), 0, 100),
                               henti_setelah=_angka(d.get("henti_setelah"), 1, 365), notif_token=None)
        try:
            setel(a)
        except SystemExit as e:
            return {"status": "gagal", "pesan": str(e)}
        return {"status": "siap", "pesan": "Pengaturan disimpan."}
    if aksi == "tambah":
        hari = _angka(d.get("hari"), 1, 3660)
        if not hari:
            return {"status": "gagal", "pesan": "Isi lama langganan (hari)."}
        r = _proses_satu({**d, "token": c.get("id")}, reg, demo=bool(d.get("demo")), hari=hari,
                         maks_siswa=_angka(d.get("maks_siswa"), 0, 100000, 0))
        if r["status"] == "siap":
            r["pesan"] = f"Sekolah {r['kode']} dibuat, aktif sampai {r['sampai']}."
        return r
    return {"status": "gagal", "pesan": "Aksi tidak dikenal."}


def _proses_perintah():
    folder = _dir_perintah()
    _, hasil = _antrean()
    if not os.path.isdir(folder):
        return
    for nama_file in sorted(os.listdir(folder)):
        if not nama_file.endswith(".json") or nama_file.startswith("."):
            continue
        path = os.path.join(folder, nama_file)
        pid = os.path.splitext(nama_file)[0]
        try:
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
            r = _jalankan_perintah({**c, "id": pid}) if isinstance(c, dict) else \
                {"status": "gagal", "pesan": "Perintah rusak."}
        except (OSError, ValueError):
            r = {"status": "gagal", "pesan": "Perintah rusak."}
        except SystemExit as e:
            r = {"status": "gagal", "pesan": str(e)[:300]}
        r.update(id=pid, selesai=datetime.now().isoformat(timespec="seconds"))
        _tulis_json(os.path.join(hasil, f"{pid}.json"), r, mode=0o640, milik_presensi=True)
        os.remove(path)
        print(f"perintah {pid}: {r['status']} {r.get('pesan', '')}")


def _tunggu_siap(port, detik=40):
    if TANPA_SISTEM:
        return True
    import time
    import urllib.request
    for _ in range(detik * 2):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/login", timeout=2)
            return True
        except Exception:  # noqa: BLE001 — layanan masih menyala
            time.sleep(0.5)
    return False


def _beritahu_vendor(pesan):
    """Kirim WA ke nomor vendor lewat Fonnte (bila token diatur dengan `setel --notif-token`)."""
    token, wa = _rahasia().get("fonnte_token"), konfigurasi()["wa"]
    if not (token and wa) or TANPA_SISTEM:
        return
    try:
        import requests
        requests.post("https://api.fonnte.com/send", headers={"Authorization": token},
                      data={"target": wa, "message": pesan}, timeout=15)
    except Exception as e:  # noqa: BLE001 — notifikasi tidak boleh menggagalkan pendaftaran
        print(f"Notifikasi WA gagal: {e}", file=sys.stderr)


def _proses_satu(p, reg, demo=True, hari=None, maks_siswa=0):
    """Buat sekolah dari permintaan formulir web (demo) atau panel vendor (demo=False)."""
    from daftar import CADANGAN, JENJANG, TOKEN_RE, ZONA, normal_wa
    k = konfigurasi()
    kode = str(p.get("kode") or "")
    nama = str(p.get("nama_sekolah") or "").strip()
    wa = normal_wa(str(p.get("wa") or ""))
    h = str(p.get("password_hash") or "")
    if (not TOKEN_RE.match(str(p.get("token") or "")) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", kode)
            or kode in CADANGAN or not 3 <= len(nama) <= 120 or not wa
            or p.get("zona") not in ZONA or p.get("jenjang") not in JENJANG
            or not re.fullmatch(r"(scrypt|pbkdf2):[A-Za-z0-9:$+/=._-]{20,250}", h)):
        return {"status": "gagal", "pesan": "Data pendaftaran tidak valid. Silakan isi ulang."}
    if kode in reg:
        return {"status": "gagal", "pesan": f"Kode “{kode}” sudah dipakai. Pilih kode lain."}
    if demo and sum(1 for s in reg.values() if _demo_aktif(s)) >= int(k["maks_demo"]):
        return {"status": "gagal", "pesan": "Kuota demo sedang penuh. Hubungi kami lewat WhatsApp."}
    a = argparse.Namespace(kode=kode, nama=nama, hari=int(hari or k["hari_demo"]), sampai=None,
                           maks_siswa=int(maks_siswa or 0), zona=p["zona"], uji_coba=demo)
    try:
        s = tambah(a, reg)
    except SystemExit as e:
        print(f"[{kode}] gagal dibuat: {e}", file=sys.stderr)
        return {"status": "gagal", "pesan": "Server gagal membuat aplikasi. Kami akan menghubungi Anda."}
    nama_admin = str(p.get("nama") or "Administrator")[:80]
    _jalankan_di_sekolah(kode, s, (
        "from app.db import connect\nfrom app import config\n"
        "db = connect(config.database())\n"
        "db.execute('UPDATE users SET password_hash = ?, nama = ?, wajib_ganti = 0 "
        f"WHERE username = ?', ({h!r}, {nama_admin!r}, 'admin'))\n"
        "db.commit()\ndb.close()\n"))
    reg = muat()
    reg[kode]["pendaftar"] = {
        "nama": nama_admin, "jabatan": str(p.get("jabatan") or "")[:60], "wa": wa,
        "email": str(p.get("email") or "")[:120], "kota": str(p.get("kota") or "")[:80],
        "jenjang": p["jenjang"], "jumlah_siswa": int(p.get("jumlah_siswa") or 0),
        "ip": str(p.get("ip") or ""), "waktu": str(p.get("dibuat") or "")}
    simpan(reg)
    _tulis_vendor(kode, reg[kode])
    _chown(kode)
    if not _tunggu_siap(s["port"]):
        print(f"[{kode}] layanan belum menjawab setelah 40 detik", file=sys.stderr)
    pd = reg[kode]["pendaftar"]
    if demo:
        _beritahu_vendor(
            f"Pendaftar demo baru\nSekolah: {nama} ({pd['jenjang']}, {pd['kota']})\n"
            f"Alamat: https://{DOMAIN}/{kode}\nNama: {pd['nama']} {('— ' + pd['jabatan']) if pd['jabatan'] else ''}\n"
            f"WA: https://wa.me/{wa}\nPerkiraan siswa: {pd['jumlah_siswa']}\nDemo sampai: {s['sampai']}")
    return {"status": "siap", "kode": kode, "url": f"https://{DOMAIN}/{kode}/login",
            "username": "admin", "sampai": s["sampai"]}


def proses_antrean(_a=None):
    """Proses permintaan demo dari halaman depan (dipicu systemd presensi-antrean.path)."""
    import fcntl
    masuk, hasil = _antrean()
    os.makedirs(masuk, exist_ok=True)
    os.makedirs(hasil, exist_ok=True)
    with open(os.path.join(ROOT, "_antrean", ".kunci"), "w") as kunci:
        fcntl.flock(kunci, fcntl.LOCK_EX)          # satu proses dalam satu waktu
        for nama_file in sorted(os.listdir(masuk)):
            if not nama_file.endswith(".json") or nama_file.startswith("."):
                continue
            path = os.path.join(masuk, nama_file)
            try:
                with open(path, encoding="utf-8") as f:
                    p = json.load(f)
                if not isinstance(p, dict):
                    raise ValueError
            except (OSError, ValueError):
                os.remove(path)
                continue
            token = os.path.splitext(nama_file)[0]
            r = _proses_satu({**p, "token": token}, muat())
            r.update(token=token, nama_sekolah=str(p.get("nama_sekolah") or "")[:120],
                     kode=r.get("kode") or str(p.get("kode") or "")[:31],
                     wa=str(p.get("wa") or "")[:20], ip=str(p.get("ip") or "")[:64],
                     dibuat=str(p.get("dibuat") or "")[:25],
                     selesai=datetime.now().isoformat(timespec="seconds"))
            _tulis_json(os.path.join(hasil, f"{token}.json"), r, mode=0o640, milik_presensi=True)
            os.remove(path)
            print(f"{token}: {r['status']} {r.get('kode', '')} {r.get('pesan', '')}")
        _proses_perintah()
        _tulis_ringkasan()


def rapikan(_a=None):
    """Harian: hentikan layanan demo yang sudah lama berakhir (data tetap disimpan) agar RAM
    VPS tidak habis, dan hapus berkas hasil pendaftaran lama."""
    k = konfigurasi()
    reg = muat()
    batas = (date.today() - timedelta(days=int(k["henti_setelah"]))).isoformat()
    berubah = False
    for kode, s in reg.items():
        if s.get("status") == "uji_coba" and s.get("sampai") and s["sampai"] < batas:
            sh("systemctl", "disable", "--now", f"presensi@{kode}", cek=False)
            s["status"] = "berhenti"
            _tulis_vendor(kode, s)
            berubah = True
            print(f"{kode}: demo berakhir {s['sampai']} — layanan dihentikan (data disimpan)")
    if berubah:
        simpan(reg)
        _tulis_map(reg)
    else:
        _tulis_publik(reg)
    _, hasil = _antrean()
    lama = (datetime.now() - timedelta(days=90)).timestamp()
    if os.path.isdir(hasil):
        for f in os.listdir(hasil):
            if os.path.getmtime(os.path.join(hasil, f)) < lama:
                os.remove(os.path.join(hasil, f))


def akun_vendor(a):
    """Buat/ganti akun panel vendor https://<domain>/vendor (password + kode Google Authenticator)."""
    import base64
    import getpass

    from werkzeug.security import generate_password_hash
    pw = a.password if a.password is not None else getpass.getpass("Password panel vendor (min. 10): ")
    if a.password is None and pw != getpass.getpass("Ulangi password: "):
        raise SystemExit("Password tidak sama.")
    if len(pw) < 10:
        raise SystemExit("Password minimal 10 karakter.")
    rahasia = base64.b32encode(secrets.token_bytes(20)).decode()
    path = os.path.join(ROOT, "_daftar", "vendor_akun.json")
    _tulis_json(path, {"username": a.username, "password_hash": generate_password_hash(pw),
                       "totp": rahasia, "versi": secrets.token_hex(8),   # ganti akun = sesi lama keluar
                       "dibuat": datetime.now().isoformat(timespec="seconds")},
                mode=0o600, milik_presensi=True)
    uri = f"otpauth://totp/{DOMAIN}:{a.username}?secret={rahasia}&issuer={DOMAIN}"
    print(f"\nAkun panel vendor dibuat: https://{DOMAIN}/vendor  (username: {a.username})")
    print("Buka Google Authenticator -> + -> Scan kode QR (atau 'Masukkan kunci penyiapan'):")
    if not a.tanpa_qr:
        try:
            import qrcode
            q = qrcode.QRCode(border=1)
            q.add_data(uri)
            q.print_ascii(invert=True)
        except Exception:  # noqa: BLE001
            pass
    print(f"Kunci penyiapan: {rahasia}")
    print("Simpan kunci ini di tempat aman (untuk memasang ulang di HP baru).")
    return rahasia


def info(a):
    reg = muat()
    if a.kode not in reg:
        raise SystemExit(f"Sekolah {a.kode} tidak ada.")
    s = {k: v for k, v in reg[a.kode].items() if k != "db_pass"}
    print(json.dumps(s, indent=1, ensure_ascii=False))


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
    p = sub.add_parser("setel")
    p.add_argument("--wa", help="nomor WhatsApp vendor, mis. 081234567890")
    p.add_argument("--nama", help="nama merek, mis. Presensiku")
    p.add_argument("--hari-demo", type=int)
    p.add_argument("--maks-demo", type=int, help="batas demo aktif bersamaan (RAM VPS)")
    p.add_argument("--henti-setelah", type=int, help="hari setelah demo habis sebelum dihentikan")
    p.add_argument("--notif-token", help="token Fonnte untuk WA pemberitahuan pendaftar baru")
    p.set_defaults(fn=setel)
    sub.add_parser("proses-antrean").set_defaults(fn=proses_antrean)
    sub.add_parser("rapikan").set_defaults(fn=rapikan)
    p = sub.add_parser("info")
    p.add_argument("kode")
    p.set_defaults(fn=info)
    p = sub.add_parser("akun-vendor")
    p.add_argument("--username", default="vendor")
    p.add_argument("--password", help=argparse.SUPPRESS)       # untuk pengujian
    p.add_argument("--tanpa-qr", action="store_true")
    p.set_defaults(fn=akun_vendor)
    a = ap.parse_args(argv)
    if a.cmd == "backup" and not a.semua and not a.kode:
        ap.error("sebutkan kode sekolah atau --semua")
    return a.fn(a)


if __name__ == "__main__":
    main()
