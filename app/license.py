"""Sistem lisensi berjenjang (Basic / Pro / Enterprise) dengan tanda tangan digital Ed25519.

- Vendor memegang KUNCI PRIVAT (vendor/private_key.pem, tidak pernah ikut dibagikan).
- Aplikasi sekolah hanya membawa KUNCI PUBLIK (app/license_public.pem) — cukup untuk
  memeriksa keaslian lisensi, mustahil dipakai membuat lisensi baru. Jadi walaupun .exe
  dibongkar, lisensi tetap tidak bisa dipalsukan.

Format kode lisensi:  PSD1-<payload base64url>.<tanda tangan base64url>
Payload (JSON): lid (ID lisensi), tier, sekolah, device (ID perangkat), exp (YYYY-MM-DD
atau null = selamanya), iat (tanggal terbit).

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

TIERS = ["basic", "pro", "enterprise"]
TIER_LABEL = {"basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}
PREFIX = "PSD1-"
WARN_DAYS = 30  # peringatan menjelang kedaluwarsa

# Alamat server aktivasi bawaan (bisa diganti admin sekolah di halaman Lisensi).
# Vendor: isi dengan URL server aktivasi Anda sebelum build, mis. "https://lisensi.domainanda.com"
DEFAULT_SERVER_URL = os.environ.get("PRESENSI_LICENSE_SERVER", "")

# Fitur yang dibuka tiap tier (kumulatif)
_FEATURES = {
    "basic": {"presensi", "master", "rekap", "kartu"},
    "pro": {"perizinan", "pelanggaran", "whatsapp", "multiuser"},
    "enterprise": {"ibadah", "multicabang"},
}

FEATURE_LABEL = {
    "perizinan": "Modul Perizinan",
    "pelanggaran": "Rekap Pelanggaran",
    "whatsapp": "Notifikasi WhatsApp",
    "multiuser": "Multi-user & Role",
    "ibadah": "Modul Ibadah",
    "multicabang": "Dashboard Multi-Cabang",
}


def features_for(tier):
    out = set()
    for t in TIERS[:TIERS.index(tier) + 1]:
        out |= _FEATURES[t]
    return out


def min_tier(feature):
    for t in TIERS:
        if feature in _FEATURES[t]:
            return t
    return "enterprise"


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


def make_license(private_key, device, tier, sekolah="", exp=None, lid=None):
    """Terbitkan kode lisensi. `exp`: date/str YYYY-MM-DD atau None (tanpa batas)."""
    tier = tier.lower()
    if tier not in TIERS:
        raise ValueError("tier harus basic/pro/enterprise")
    if isinstance(exp, (date, datetime)):
        exp = exp.strftime("%Y-%m-%d")
    obj = {"lid": lid or uuid.uuid4().hex[:12].upper(), "tier": tier, "sekolah": sekolah or "",
           "device": device.strip().upper(), "exp": exp, "iat": date.today().isoformat()}
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
    out = {"valid": False, "reason": "", "tier": "basic", "sekolah": "", "lid": None,
           "exp": None, "days_left": None, "payload": None}
    key = (key or "").strip()
    if not key:
        out["reason"] = "Belum ada lisensi (mode Basic)."
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
    out.update(payload=p, tier=p.get("tier", "basic"), sekolah=p.get("sekolah", ""),
               lid=p.get("lid"), exp=p.get("exp"))
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
    info = current_license(db)
    return info["tier"] if info["valid"] else "basic"


def has_feature(feature, db=None):
    return feature in features_for(current_tier(db))


def touch_last_seen(db):
    """Catat tanggal terbaru yang pernah terlihat (deteksi jam komputer dimundurkan)."""
    from .db import get_setting, set_setting
    today = _today().isoformat()
    if (get_setting("license_last_seen", db=db) or "") < today:
        set_setting("license_last_seen", today, db=db)
