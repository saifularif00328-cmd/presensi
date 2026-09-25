"""Sistem lisensi berjenjang (Basic / Pro / Enterprise).

Kode lisensi = tanda tangan HMAC atas (ID perangkat + tier) memakai secret vendor.
Kode hanya valid di perangkat yang ID-nya dipakai saat membuat kode. Kode dibuat
oleh vendor dengan `python tools/keygen.py <ID_PERANGKAT> <tier>`.

PENTING: ganti nilai default VENDOR_SECRET di bawah
sebelum aplikasi didistribusikan.
"""
import base64
import hashlib
import hmac
import os
import platform
import uuid

VENDOR_SECRET = os.environ.get("PRESENSI_VENDOR_SECRET", "ganti-secret-vendor-sebelum-rilis")

TIERS = ["basic", "pro", "enterprise"]
TIER_LABEL = {"basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}

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
        return override
    h = hashlib.sha256(_machine_fingerprint().encode()).hexdigest().upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def make_key(dev_id, tier, secret=None):
    tier = tier.lower()
    if tier not in TIERS:
        raise ValueError("tier harus basic/pro/enterprise")
    mac = hmac.new((secret or VENDOR_SECRET).encode(),
                   f"{dev_id.upper()}|{tier}".encode(), hashlib.sha256).digest()
    code = base64.b32encode(mac)[:20].decode()
    return f"{TIER_LABEL[tier].upper()}-" + "-".join(code[i:i + 5] for i in range(0, 20, 5))


def validate_key(key, dev_id=None):
    """Kembalikan tier bila kode valid untuk perangkat ini, else None."""
    if not key:
        return None
    key = key.strip().upper()
    dev_id = dev_id or device_id()
    for tier in TIERS:
        if hmac.compare_digest(key, make_key(dev_id, tier)):
            return tier
    return None


def current_tier(db=None):
    from .db import get_setting
    return validate_key(get_setting("license_key", db=db)) or "basic"


def has_feature(feature, db=None):
    return feature in features_for(current_tier(db))
