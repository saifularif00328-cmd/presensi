"""Lisensi langganan (satu paket, semua fitur) dengan tanda tangan digital Ed25519.

Status langganan sekolah: uji coba (14 hari sejak instalasi, tanpa kode) -> aktif (kode
lisensi valid) -> masa tenggang (7 hari setelah berakhir) -> habis (mode baca-saja: data
tetap bisa dilihat & diekspor, tetapi tidak bisa absen / mengubah data).
Server VPS milik vendor (PRESENSI_MODE=cloud) membaca status dari berkas data/_vendor.json.

- Vendor memegang KUNCI PRIVAT (vendor/private_key.pem, tidak pernah ikut dibagikan).
- Aplikasi sekolah hanya membawa KUNCI PUBLIK (app/license_public.pem) — cukup untuk
  memeriksa keaslian lisensi, mustahil dipakai membuat lisensi baru. Jadi walaupun .exe
  dibongkar, lisensi tetap tidak bisa dipalsukan.

Format kode lisensi:  PSD1-<payload base64url>.<tanda tangan base64url>
Payload (JSON): lid (ID lisensi), tier (lama; kini diabaikan — semua fitur aktif), sekolah,
device (ID perangkat), exp (YYYY-MM-DD atau null = selamanya), iat (tanggal terbit),
maks_siswa (0/null = tanpa batas).

Lisensi dibuat oleh vendor lewat server aktivasi (license_server/) atau secara offline
dengan `python tools/keygen.py`. Kunci dibuat sekali dengan `python tools/vendor_init.py`.
"""
import base64
import hashlib
import json
import os
import platform
import uuid
from datetime import date, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TIERS = ["lengkap", "basic", "pro", "enterprise"]  # tier lama tetap diterima (setara lengkap)
TIER_LABEL = {"lengkap": "Paket Lengkap", "basic": "Paket Lengkap", "pro": "Paket Lengkap",
              "enterprise": "Paket Lengkap"}
PREFIX = "PSD1-"
WARN_DAYS = 14      # pengingat menjelang berakhir
TRIAL_DAYS = 14     # uji coba tanpa kode lisensi
GRACE_DAYS = 7      # masa tenggang setelah berakhir

# Alamat server aktivasi bawaan (bisa diganti admin sekolah di halaman Lisensi).
# Vendor: isi dengan URL server aktivasi Anda sebelum build, mis. "https://lisensi.domainanda.com"
DEFAULT_SERVER_URL = os.environ.get("PRESENSI_LICENSE_SERVER", "")

FEATURE_LABEL = {
    "perizinan": "Modul Perizinan",
    "pelanggaran": "Rekap Pelanggaran",
    "whatsapp": "Notifikasi WhatsApp",
    "multiuser": "Multi-user & Role",
    "ibadah": "Modul Ibadah",
    "multicabang": "Dashboard Multi-Cabang",
}


def features_for(_tier=None):
    """Satu paket: semua fitur tersedia (pembatasan kini lewat status langganan)."""
    return {"presensi", "master", "rekap", "kartu", *FEATURE_LABEL}


def min_tier(_feature):
    return "lengkap"


# ------------------------------------------------------------------ ID perangkat
def _machine_fingerprint():
    parts = [platform.node(), platform.machine(), str(uuid.getnode())]
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, encoding="utf-8") as f:
                parts.append(f.read().strip())
                break
        except OSError:
            pass
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\Microsoft\Cryptography",
                                 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            parts.append(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    return "|".join(parts)


def device_id():
    override = os.environ.get("PRESENSI_DEVICE_ID")
    if override:
        return override.upper()
    h = hashlib.sha256(_machine_fingerprint().encode()).hexdigest().upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


# ------------------------------------------------------------------ kunci
def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _public_key_path():
    from . import config
    return os.path.join(config.BUNDLE_DIR, "license_public.pem")


_PUB_CACHE = {}


def public_key():
    """Kunci publik vendor: env PRESENSI_LICENSE_PUBKEY (PEM) atau app/license_public.pem."""
    pem = os.environ.get("PRESENSI_LICENSE_PUBKEY")
    if not pem:
        try:
            with open(_public_key_path(), encoding="utf-8") as f:
                pem = f.read()
        except OSError:
            return None
    if pem not in _PUB_CACHE:
        try:
            _PUB_CACHE[pem] = serialization.load_pem_public_key(pem.encode())
        except ValueError:
            _PUB_CACHE[pem] = None
    return _PUB_CACHE[pem]


def load_private_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def generate_keypair():
    """(private_pem, public_pem) baru — dipakai tools/vendor_init.py."""
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())
    pub_pem = priv.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)
    return priv_pem, pub_pem


# ------------------------------------------------------------------ buat & periksa
def _sign(private_key, obj):
    payload = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    return _b64e(payload) + "." + _b64e(private_key.sign(payload))


def _verify(token, pub=None):
    """Kembalikan dict payload bila tanda tangan valid, else None."""
    pub = pub or public_key()
    if pub is None or not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    try:
        payload = _b64d(body)
        pub.verify(_b64d(sig), payload)
        return json.loads(payload)
    except (InvalidSignature, ValueError, TypeError):
        return None


def make_license(private_key, device, tier="lengkap", sekolah="", exp=None, lid=None,
                 maks_siswa=0):
    """Terbitkan kode lisensi. `exp`: date/str YYYY-MM-DD atau None (tanpa batas)."""
    tier = (tier or "lengkap").lower()
    if tier not in TIERS:
        raise ValueError("tier tidak dikenal")
    if isinstance(exp, (date, datetime)):
        exp = exp.strftime("%Y-%m-%d")
    obj = {"lid": lid or uuid.uuid4().hex[:12].upper(), "tier": tier, "sekolah": sekolah or "",
           "device": device.strip().upper(), "exp": exp, "iat": date.today().isoformat(),
           "maks_siswa": int(maks_siswa or 0)}
    return PREFIX + _sign(private_key, obj)


def sign_status(private_key, lid, device, status):
    """Pernyataan status bertanda tangan dari server (mis. 'aktif' / 'dicabut')."""
    return _sign(private_key, {"lid": lid, "device": device, "status": status,
                               "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


def verify_status(token):
    return _verify(token)


def _today():
    from . import utils
    return utils.today()


def parse_license(key, dev=None, today=None, last_seen=None):
    """Periksa kode lisensi. Selalu mengembalikan dict:
    valid (bool), reason (str), tier, sekolah, lid, exp, days_left (int/None), payload."""
    out = {"valid": False, "reason": "", "tier": "lengkap", "sekolah": "", "lid": None,
           "exp": None, "days_left": None, "payload": None, "maks_siswa": 0, "expired": False}
    key = (key or "").strip()
    if not key:
        out["reason"] = "Belum ada kode lisensi."
        return out
    if public_key() is None:
        out["reason"] = "Kunci publik vendor belum dipasang di aplikasi."
        return out
    if not key.startswith(PREFIX):
        out["reason"] = "Format kode lisensi tidak dikenali."
        return out
    p = _verify(key[len(PREFIX):])
    if p is None:
        out["reason"] = "Tanda tangan lisensi tidak valid (kode rusak atau palsu)."
        return out
    out.update(payload=p, tier=p.get("tier") or "lengkap", sekolah=p.get("sekolah", ""),
               lid=p.get("lid"), exp=p.get("exp"), maks_siswa=int(p.get("maks_siswa") or 0))
    if p.get("device", "").upper() != (dev or device_id()).upper():
        out["reason"] = "Lisensi ini untuk perangkat lain."
        return out
    today = today or _today()
    if last_seen and today < last_seen - timedelta(days=2):
        out["reason"] = "Tanggal komputer mundur. Perbaiki tanggal & jam sistem."
        return out
    if out["exp"]:
        exp = datetime.strptime(out["exp"], "%Y-%m-%d").date()
        out["days_left"] = (exp - today).days
        if today > exp:
            out["reason"] = f"Lisensi kedaluwarsa sejak {out['exp']}."
            out["expired"] = True
            return out
    if out["tier"] not in TIERS:
        out["reason"] = "Tier tidak dikenal."
        return out
    out["valid"] = True
    return out


# ------------------------------------------------------------------ status aktif aplikasi
_CACHE = {}


def current_license(db=None):
    """Status lisensi aplikasi saat ini (di-cache per tanggal & isi pengaturan)."""
    from .db import get_setting
    key = get_setting("license_key", db=db) or ""
    status = get_setting("license_status", db=db) or ""
    seen = get_setting("license_last_seen", db=db) or ""
    today = _today()
    ck = (key, status, seen, today, os.environ.get("PRESENSI_LICENSE_PUBKEY"))
    if ck not in _CACHE:
        last_seen = datetime.strptime(seen, "%Y-%m-%d").date() if seen else None
        info = parse_license(key, today=today, last_seen=last_seen)
        if info["valid"] and status == "dicabut":
            info["valid"] = False
            info["reason"] = "Lisensi telah dicabut oleh vendor."
        _CACHE.clear()
        _CACHE[ck] = info
    return _CACHE[ck]


def current_tier(db=None):
    return "lengkap"


def has_feature(_feature, db=None):
    """Semua fitur termasuk paket. Pembatasan saat langganan habis: lihat langganan()."""
    return True


def _cloud_status(today):
    """Status dari berkas vendor (hanya di server VPS vendor, PRESENSI_MODE=cloud)."""
    from . import config
    path = os.path.join(config.DATA_DIR, "_vendor.json")
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return {"status": "habis", "sampai": None, "maks_siswa": 0,
                "alasan": "Berkas status vendor (_vendor.json) tidak ada atau rusak."}
    sampai = v.get("berlaku_sampai")
    out = {"status": "aktif", "sampai": sampai, "maks_siswa": int(v.get("maks_siswa") or 0),
           "alasan": "", "wa_vendor": v.get("wa_vendor") or "",
           "nama_vendor": v.get("nama_vendor") or "", "kode": v.get("kode") or "",
           "demo": bool(v.get("demo"))}
    if v.get("status") == "uji_coba":
        out["status"] = "uji_coba"
    if v.get("status") == "nonaktif":
        out.update(status="habis", alasan="Langganan dinonaktifkan oleh vendor.")
    return out


def langganan(db=None):
    """Status langganan sekolah saat ini:
    status  : aktif / uji_coba / tenggang / habis
    sampai  : tanggal berakhir (YYYY-MM-DD) atau None (tanpa batas)
    sisa    : sisa hari (int/None); tenggang = sisa hari masa tenggang
    maks_siswa, alasan, label, baca_saja (bool), peringatan (bool)
    """
    from .db import get_setting
    today = _today()
    if os.environ.get("PRESENSI_MODE") == "cloud":
        out = _cloud_status(today)
    else:
        info = current_license(db)
        if info["valid"]:
            out = {"status": "aktif", "sampai": info["exp"], "maks_siswa": info["maks_siswa"],
                   "alasan": ""}
        elif info["expired"] and get_setting("license_status", db=db) != "dicabut":
            out = {"status": "aktif", "sampai": info["exp"], "maks_siswa": info["maks_siswa"],
                   "alasan": info["reason"]}
        elif (get_setting("license_key", db=db) or "").strip():
            out = {"status": "habis", "sampai": None, "maks_siswa": 0, "alasan": info["reason"]}
        else:
            mulai = get_setting("install_date", db=db) or today.isoformat()
            akhir = datetime.strptime(mulai, "%Y-%m-%d").date() + timedelta(days=TRIAL_DAYS)
            out = {"status": "uji_coba", "sampai": akhir.isoformat(), "maks_siswa": 0,
                   "alasan": ""}
    out["sisa"] = None
    if out["status"] != "habis" and out.get("sampai"):
        sampai = datetime.strptime(out["sampai"], "%Y-%m-%d").date()
        sisa = (sampai - today).days
        out["sisa"] = sisa
        if sisa < 0:
            batas_tenggang = 0 if out["status"] == "uji_coba" else GRACE_DAYS
            if -sisa <= batas_tenggang:
                out.update(status="tenggang", sisa=batas_tenggang + sisa)
            else:
                out.update(status="habis", sisa=None,
                           alasan=out["alasan"] or f"Masa langganan berakhir {out['sampai']}.")
    for kunci, bawaan in (("wa_vendor", ""), ("nama_vendor", ""), ("kode", ""), ("demo", False)):
        out.setdefault(kunci, bawaan)
    out["label"] = {"aktif": "Aktif", "uji_coba": "Uji coba", "tenggang": "Masa tenggang",
                    "habis": "Habis"}[out["status"]]
    out["baca_saja"] = out["status"] == "habis"
    out["peringatan"] = (out["status"] in ("uji_coba", "tenggang", "habis")
                         or (out["sisa"] is not None and out["sisa"] <= WARN_DAYS))
    return out


def touch_last_seen(db):
    """Catat tanggal terbaru yang pernah terlihat (deteksi jam komputer dimundurkan)."""
    from .db import get_setting, set_setting
    today = _today().isoformat()
    if (get_setting("license_last_seen", db=db) or "") < today:
        set_setting("license_last_seen", today, db=db)


def tautan_perpanjang(L, nama_pengguna=""):
    """Tautan wa.me ke vendor berisi pesan permintaan perpanjangan lisensi ('' bila nomor WA
    vendor belum diatur dengan `presensi-sekolah setel --wa ...`)."""
    if not L.get("wa_vendor"):
        return ""
    from urllib.parse import quote
    from .db import get_setting, query
    from .utils import tanggal_indo
    n = query("SELECT COUNT(*) AS n FROM siswa WHERE aktif = 1", one=True)["n"]
    masa = "demo" if L.get("demo") else "langganan"
    if L["status"] == "habis":
        kapan = f"sudah berakhir{(' pada ' + tanggal_indo(L['sampai'])) if L.get('sampai') else ''}"
    elif L.get("sampai"):
        kapan = f"akan berakhir pada {tanggal_indo(L['sampai'])}"
    else:
        kapan = "akan berakhir"
    pesan = (f"Halo {L.get('nama_vendor') or 'Admin'}, saya {nama_pengguna or 'admin'} dari "
             f"{get_setting('nama_sekolah') or 'sekolah kami'}"
             f"{(' (kode: ' + L['kode'] + ')') if L.get('kode') else ''}.\n"
             f"Masa {masa} aplikasi Presensi Siswa Digital kami {kapan}.\n"
             f"Kami ingin memperpanjang lisensi.\n"
             f"Jumlah siswa aktif: {n}\n"
             f"Mohon info paket dan cara pembayarannya. Terima kasih.")
    return f"https://wa.me/{L['wa_vendor']}?text={quote(pesan)}"
