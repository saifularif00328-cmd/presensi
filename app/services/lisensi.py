"""Aktivasi & pengecekan lisensi online ke server aktivasi vendor.

Aplikasi tetap offline-first: lisensi yang sudah aktif tetap berlaku tanpa internet
sampai tanggal kedaluwarsanya. Saat online, aplikasi mengecek status lisensi sekali
sehari (pencabutan / perpanjangan otomatis)."""
import requests

from .. import config, utils
from ..db import get_setting, set_setting
from ..license import (DEFAULT_SERVER_URL, current_license, device_id, parse_license,
                       verify_status)


def server_url(db=None):
    return (get_setting("license_server", db=db) or DEFAULT_SERVER_URL or "").rstrip("/")


def _post(url, data, timeout=15):
    r = requests.post(url, json=data, timeout=timeout)
    try:
        return r.json()
    except ValueError:
        return {"ok": False, "error": f"Respons server tidak valid (HTTP {r.status_code})"}


def _save(db, key, status="aktif"):
    set_setting("license_key", key, db=db, commit=False)
    set_setting("license_status", status, db=db, commit=False)
    set_setting("license_checked", utils.now().strftime("%Y-%m-%d %H:%M"), db=db)


def activate_offline(db, key):
    info = parse_license(key)
    if info["valid"]:
        _save(db, key.strip())
    return info


def activate_online(db, url, code):
    """Tukar kode aktivasi dengan lisensi bertanda tangan dari server. (ok, pesan)."""
    url = (url or "").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        return False, "Alamat server aktivasi harus diawali http:// atau https://"
    try:
        res = _post(f"{url}/api/activate", {
            "code": code.strip().upper(), "device": device_id(),
            "sekolah": get_setting("nama_sekolah", db=db), "app_version": config.APP_VERSION})
    except requests.RequestException as e:
        return False, f"Tidak dapat menghubungi server aktivasi ({type(e).__name__})."
    if not res.get("ok"):
        return False, res.get("error") or "Aktivasi ditolak server."
    info = parse_license(res.get("license", ""))
    if not info["valid"]:
        return False, f"Lisensi dari server tidak valid: {info['reason']}"
    set_setting("license_server", url, db=db, commit=False)
    _save(db, res["license"])
    return True, info


def check_online(db):
    """Cek status lisensi ke server (dipanggil harian oleh scheduler). Mengembalikan
    status ('aktif'/'dicabut'), atau None bila tidak bisa dicek (offline, tanpa server)."""
    info = current_license(db)
    url = server_url(db)
    if not url or not info.get("lid"):
        return None
    try:
        res = _post(f"{url}/api/check", {"lid": info["lid"], "device": device_id(),
                                         "app_version": config.APP_VERSION}, timeout=10)
    except requests.RequestException:
        return None
    st = verify_status(res.get("status_token", ""))
    if not st or st.get("lid") != info["lid"] or st.get("device", "").upper() != device_id():
        return None
    status = st.get("status")
    if status not in ("aktif", "dicabut"):
        return None
    new_key = res.get("license")
    if status == "aktif" and new_key and new_key != get_setting("license_key", db=db):
        baru = parse_license(new_key)
        if baru["valid"] and baru["lid"] == info["lid"]:  # perpanjangan / ganti tier
            _save(db, new_key)
            return status
    set_setting("license_status", status, db=db, commit=False)
    set_setting("license_checked", utils.now().strftime("%Y-%m-%d %H:%M"), db=db)
    return status
