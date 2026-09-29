"""Simulator perangkat tap RFID (meniru ESP32) — untuk menguji server tanpa alat.

    python tools/simulasi_perangkat.py --server https://smpn1.presensiku.biz.id \\
        --kode ESP-1A2B3C --rahasia <rahasia> ping
    python tools/simulasi_perangkat.py --server http://localhost:5000 --kode ... --rahasia ... \\
        tap A1B2C3D4
    python tools/simulasi_perangkat.py ... tap A1B2C3D4 --menit-lalu 30   # tap offline 30 menit lalu
    python tools/simulasi_perangkat.py ... interaktif                    # ketik UID berulang

Kode & rahasia ada di aplikasi: Sistem → Perangkat RFID → Isian.
Protokol sama persis dengan firmware/esp32_rfid (HMAC-SHA256, nonce, waktu).
"""
import argparse
import hashlib
import hmac
import json
import secrets
import sys
import time

import requests


def kirim(server, kode, rahasia, path, body):
    raw = json.dumps(body, separators=(",", ":")).encode()
    waktu, nonce = str(int(time.time())), secrets.token_hex(8)
    tanda = hmac.new(rahasia.encode(), f"{kode}\n{waktu}\n{nonce}\n".encode() + raw,
                     hashlib.sha256).hexdigest()
    r = requests.post(server.rstrip("/") + path, data=raw, timeout=10, headers={
        "Content-Type": "application/json", "X-Perangkat": kode, "X-Waktu": waktu,
        "X-Nonce": nonce, "X-Tanda": tanda, "X-Versi": "simulator"})
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"pesan": r.text[:200]}


def lcd(status, j):
    garis = "+" + "-" * 18 + "+"
    print(garis)
    print(f"| {str(j.get('baris1', ''))[:16]:<16} |")
    print(f"| {str(j.get('baris2', ''))[:16]:<16} |")
    print(garis, f"HTTP {status}, nada: {j.get('nada', '-')}")
    if j.get("pesan"):
        print("  ", j["pesan"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--server", required=True)
    ap.add_argument("--kode", required=True)
    ap.add_argument("--rahasia", required=True)
    ap.add_argument("aksi", choices=["ping", "tap", "interaktif"])
    ap.add_argument("uid", nargs="?")
    ap.add_argument("--menit-lalu", type=int, default=0, help="kirim sebagai tap tertunda")
    a = ap.parse_args()
    if a.aksi == "ping":
        lcd(*kirim(a.server, a.kode, a.rahasia, "/api/perangkat/ping", {}))
    elif a.aksi == "tap":
        if not a.uid:
            sys.exit("UID kartu wajib diisi, mis. A1B2C3D4")
        ts = int(time.time()) - a.menit_lalu * 60
        lcd(*kirim(a.server, a.kode, a.rahasia, "/api/perangkat/tap", {"uid": a.uid, "ts": ts}))
    else:
        print("Ketik UID kartu lalu Enter (kosong = keluar).")
        while True:
            uid = input("UID> ").strip()
            if not uid:
                break
            lcd(*kirim(a.server, a.kode, a.rahasia, "/api/perangkat/tap",
                       {"uid": uid, "ts": int(time.time())}))


if __name__ == "__main__":
    main()
