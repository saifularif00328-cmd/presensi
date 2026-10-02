"""Klien API server sekolah (permintaan bertanda tangan HMAC, sama seperti perangkat ESP32)."""
import hashlib
import hmac
import json
import secrets
import time

from . import VERSI


class GalatServer(Exception):
    """Server menjawab tetapi menolak (status 4xx/5xx)."""

    def __init__(self, status, data):
        super().__init__(data.get("pesan") if isinstance(data, dict) else str(data))
        self.status = status
        self.data = data if isinstance(data, dict) else {}


class GalatJaringan(Exception):
    """Server tidak terjangkau (internet putus / DNS / timeout)."""


def _sesi_bawaan():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = f"PresensikuPos/{VERSI}"
    return s


def _post(sesi, url, data, headers, timeout):
    import requests
    try:
        r = sesi.post(url, data=data, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise GalatJaringan(str(e)) from e
    return r


class Klien:
    def __init__(self, server, kode, rahasia, sesi=None, timeout=8):
        self.server = server.rstrip("/")
        self.kode = kode
        self.rahasia = rahasia
        self.sesi = sesi or _sesi_bawaan()
        self.timeout = timeout
        self.selisih = 0           # koreksi jam PC terhadap server (detik)

    def _kirim(self, path, body, mentah=False, ulang=True):
        raw = json.dumps(body).encode()
        waktu = str(int(time.time() + self.selisih))
        nonce = secrets.token_hex(10)
        tanda = hmac.new(self.rahasia.encode(), f"{self.kode}\n{waktu}\n{nonce}\n".encode() + raw,
                         hashlib.sha256).hexdigest()
        r = _post(self.sesi, self.server + path, raw,
                  {"Content-Type": "application/json", "X-Pos": self.kode, "X-Waktu": waktu,
                   "X-Nonce": nonce, "X-Tanda": tanda, "X-Versi": VERSI}, self.timeout)
        if mentah and r.status_code == 200:
            return r.content
        try:
            data = r.json()
        except ValueError:
            raise GalatServer(r.status_code, {"pesan": f"Jawaban server tidak dikenali ({r.status_code})"})
        if r.status_code == 401 and data.get("error") == "waktu" and data.get("server_time") and ulang:
            # jam PC meleset: sesuaikan lalu ulangi sekali
            self.selisih = int(data["server_time"]) - int(time.time())
            return self._kirim(path, body, mentah, ulang=False)
        if r.status_code != 200:
            raise GalatServer(r.status_code, data)
        return data

    # ---------------------------------------------------------------- API
    @staticmethod
    def pasang(server, kode_pasang, nama_pc="", sesi=None, timeout=10):
        sesi = sesi or _sesi_bawaan()
        r = _post(sesi, server.rstrip("/") + "/api/pos/pasang",
                  json.dumps({"kode_pasang": kode_pasang, "nama_pc": nama_pc, "versi": VERSI}).encode(),
                  {"Content-Type": "application/json"}, timeout)
        try:
            data = r.json()
        except ValueError:
            raise GalatServer(r.status_code, {"pesan": "Alamat server salah — bukan aplikasi presensi."})
        if r.status_code != 200 or not data.get("ok"):
            raise GalatServer(r.status_code, data)
        return data

    def sinkron(self, antrean=0, scanner=()):
        return self._kirim("/api/pos/sinkron", {"antrean": antrean, "scanner": list(scanner)})

    def petakan(self, kunci, jenis, label, gerbang_id=None, abaikan=False):
        return self._kirim("/api/pos/scanner", {"kunci": kunci, "jenis": jenis, "label": label,
                                                 "gerbang_id": gerbang_id, "abaikan": abaikan})

    def siswa(self, versi=None):
        return self._kirim("/api/pos/siswa", {"versi": versi})

    def foto(self, siswa_id):
        return self._kirim("/api/pos/foto", {"id": siswa_id}, mentah=True)

    def scan(self, daftar):
        return self._kirim("/api/pos/scan", {"scans": list(daftar)})["hasil"]
