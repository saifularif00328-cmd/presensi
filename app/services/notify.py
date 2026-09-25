"""Notifikasi WhatsApp via Fonnte dengan antrian offline.

Alur: event presensi → `enqueue()` hanya menulis ke tabel notif_queue (cepat, tidak
menghambat scan). Job background `process_queue()` mengecek koneksi internet lalu
mengirim pesan yang tertunda. Saat offline, pesan tetap berstatus
"Menunggu Koneksi" dan otomatis terkirim begitu internet kembali.
"""
import logging

import requests

from .. import utils
from ..db import execute, get_setting, query, set_setting
from ..license import has_feature

log = logging.getLogger(__name__)

FONNTE_SEND_URL = "https://api.fonnte.com/send"
FONNTE_DEVICE_URL = "https://api.fonnte.com/device"
MAX_PERCOBAAN = 3

JENIS = {
    "masuk": "Absen Masuk",
    "pulang": "Absen Pulang",
    "alpha": "Alpha (tanpa keterangan)",
    "izin": "Izin/Sakit disetujui",
    "pelanggaran": "Pelanggaran baru",
}


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render(template, siswa, extra=None):
    data = {"nama_siswa": siswa["nama"], "kelas": siswa["kelas_nama"] or "-",
            "jam": utils.now().strftime("%H:%M"), "status": "", "keterangan": ""}
    data.update(extra or {})
    return template.format_map(_SafeDict(data))


def nomor_ortu(siswa):
    seen = []
    for key in ("wa_ayah", "wa_ibu", "wa_wali"):
        n = utils.normalize_wa(siswa[key])
        if n and n not in seen:
            seen.append(n)
    return seen


def enqueue(db, siswa, jenis, extra=None, force=False):
    """Masukkan pesan ke antrian. Tidak melakukan commit (ikut transaksi pemanggil)."""
    if not has_feature("whatsapp", db=db):
        return 0
    if not force and get_setting(f"wa_on_{jenis}", db=db) != "1":
        return 0
    tpl = get_setting(f"wa_tpl_{jenis}", db=db)
    if not tpl:
        return 0
    pesan = render(tpl, siswa, extra)
    n = 0
    for nomor in nomor_ortu(siswa):
        execute("INSERT INTO notif_queue(siswa_id, jenis, nomor, pesan) VALUES (?,?,?,?)",
                (siswa["id"], jenis, nomor, pesan), db=db, commit=False)
        n += 1
    return n


def fonnte_token(db=None):
    return utils.decrypt(get_setting("fonnte_token", db=db))


def is_online(timeout=4):
    try:
        requests.head("https://api.fonnte.com", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def send_one(token, nomor, pesan):
    r = requests.post(FONNTE_SEND_URL, headers={"Authorization": token},
                      data={"target": nomor, "message": pesan, "countryCode": "62"}, timeout=20)
    try:
        body = r.json()
    except ValueError:
        return False, f"HTTP {r.status_code}"
    if body.get("status"):
        return True, None
    return False, str(body.get("reason") or body.get("detail") or body)[:250]


def process_queue(db, limit=25):
    """Kirim pesan yang tertunda. Mengembalikan jumlah terkirim."""
    pending = query("SELECT * FROM notif_queue WHERE status = 'Menunggu Koneksi' "
                    "ORDER BY id LIMIT ?", (limit,), db=db)
    if not pending:
        return 0
    if not has_feature("whatsapp", db=db):
        return 0
    token = fonnte_token(db)
    if not token or not is_online():
        return 0
    sent = 0
    for row in pending:
        try:
            ok, err = send_one(token, row["nomor"], row["pesan"])
        except requests.RequestException as e:
            # Koneksi terputus di tengah proses → biarkan menunggu
            log.warning("Gagal kirim WA (koneksi): %s", e)
            break
        if ok:
            execute("UPDATE notif_queue SET status = 'Terkirim', error = NULL, "
                    "percobaan = percobaan + 1, sent_at = datetime('now','localtime') "
                    "WHERE id = ?", (row["id"],), db=db)
            sent += 1
        else:
            status = "Gagal" if row["percobaan"] + 1 >= MAX_PERCOBAAN else "Menunggu Koneksi"
            execute("UPDATE notif_queue SET status = ?, error = ?, percobaan = percobaan + 1 "
                    "WHERE id = ?", (status, err, row["id"]), db=db)
    return sent


def refresh_quota(db):
    """Ambil sisa kuota perangkat Fonnte (ditampilkan di dashboard admin)."""
    token = fonnte_token(db)
    if not token:
        return None
    try:
        r = requests.post(FONNTE_DEVICE_URL, headers={"Authorization": token}, timeout=15)
        body = r.json()
    except (requests.RequestException, ValueError):
        return None
    if body.get("status"):
        info = f"{body.get('quota', '-')} pesan · perangkat {body.get('device', '-')} " \
               f"({body.get('device_status', '-')})"
    else:
        info = f"Error: {body.get('reason', 'token tidak valid')}"
    set_setting("fonnte_kuota", info, db=db)
    set_setting("fonnte_kuota_cek", utils.now().strftime("%Y-%m-%d %H:%M"), db=db)
    return info
