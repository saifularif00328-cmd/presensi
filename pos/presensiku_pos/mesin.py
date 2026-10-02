"""Mesin Presensiku Pos: scanner -> gerbang -> server, antrean offline, dan umpan Layar Gerbang."""
import datetime as _dt
import logging
import os
import threading
import time
import uuid as _uuid

from . import VERSI, konfig
from .antrean import Antrean
from .data_siswa import DataSiswa
from .klien import GalatJaringan, GalatServer, Klien
from .perakit import Perakit

log = logging.getLogger(__name__)

BATAS_TUNGGU = 1.5        # detik menunggu jawaban server sebelum ditampilkan sebagai "tersimpan"
SINKRON_DETIK = 60
SISWA_DETIK = 300
MAKS_ITEM = 300


def _versi_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


class Mesin:
    def __init__(self, sesi=None, waktu=time.time):
        self.sesi = sesi                       # sesi HTTP (uji: adaptor Flask test client)
        self.waktu = waktu
        self.lock = threading.RLock()
        self.pos = konfig.baca("pos.json")             # server, kode, rahasia, nama, sekolah
        self.cfg = konfig.baca("server.json")          # gerbang, scanner, qr_secret, jeda_ganda
        self.peta_lokal = konfig.baca("peta_lokal.json")
        self.foto_versi = konfig.baca("foto.json")
        self.data = DataSiswa(konfig.baca("siswa.json"), self.cfg.get("qr_secret"))
        self.antrean = Antrean(konfig.jalur("antrean.db"))
        self.perakit = Perakit()
        self.item, self._id = [], 0
        self.tertunda = {}
        self.baru = {}
        self.terlihat = {}
        self._terakhir = {}                    # siswa_id -> epoch scan berhasil terakhir
        self._hadir, self._tanggal = {}, None
        self.online = False
        self.peringatan = ""
        self.versi_baru = None
        self._picu = threading.Event()
        self._sinkron_sekarang = threading.Event()
        self.berjalan = True
        self.klien = self._buat_klien()

    # ------------------------------------------------------------ status dasar
    def _buat_klien(self):
        p = self.pos
        if p.get("server") and p.get("kode") and p.get("rahasia"):
            return Klien(p["server"], p["kode"], p["rahasia"], sesi=self.sesi)
        return None

    @property
    def terpasang(self):
        return self.klien is not None

    def pasang(self, server, kode_pasang):
        server = konfig.normal_server(server)
        import platform
        data = Klien.pasang(server, kode_pasang, platform.node(), sesi=self.sesi)
        self.pos = {"server": server, "kode": data["kode"], "rahasia": data["rahasia"],
                    "nama": data.get("nama"), "sekolah": data.get("sekolah")}
        konfig.tulis("pos.json", self.pos, rahasia=True)
        self.klien = self._buat_klien()
        self.sinkron()
        return {"ok": True, "nama": self.pos["nama"], "sekolah": self.pos["sekolah"]}

    def _epoch(self):
        return int(self.waktu() + (self.klien.selisih if self.klien else 0))

    # ------------------------------------------------------------ scanner & gerbang
    def gerbang(self):
        return self.cfg.get("gerbang") or []

    def _nama_gerbang(self, gid):
        return next((g["nama"] for g in self.gerbang() if g["id"] == gid), None)

    def peta(self, kunci):
        """{'gerbang_id', 'gerbang', 'aktif'} atau None bila scanner belum dikenal."""
        lokal = self.peta_lokal.get(kunci)
        if lokal:
            gid = None if lokal.get("abaikan") else lokal.get("gerbang_id")
            return {"gerbang_id": gid, "gerbang": self._nama_gerbang(gid),
                    "aktif": not lokal.get("abaikan")}
        sc = next((s for s in self.cfg.get("scanner") or [] if s["kunci"] == kunci), None)
        if sc and (sc.get("gerbang_id") or not sc.get("aktif")):
            return {"gerbang_id": sc.get("gerbang_id"), "gerbang": sc.get("gerbang")
                    or self._nama_gerbang(sc.get("gerbang_id")), "aktif": bool(sc.get("aktif"))}
        return None

    def tombol(self, kunci, label, vk, turun, t=None):
        """Dari Raw Input (scanner mode keyboard)."""
        with self.lock:
            self.terlihat[kunci] = {"kunci": kunci, "jenis": "keyboard", "label": label}
            s = self.perakit.tombol(kunci, vk, turun, t)
            if s:
                self.terima(s.kunci, s.teks, s.cepat, "keyboard", label)

    def teks_com(self, kunci, label, teks):
        """Dari scanner mode COM (satu baris = satu scan)."""
        with self.lock:
            self.terlihat[kunci] = {"kunci": kunci, "jenis": "com", "label": label}
            s = self.perakit.teks(kunci, teks)
            if s:
                self.terima(s.kunci, s.teks, True, "com", label)

    def terima(self, kunci, teks, cepat, jenis, label):
        with self.lock:
            m = self.peta(kunci)
            if m and not m["aktif"]:
                return                                   # diabaikan (keyboard biasa)
            if m and m["gerbang_id"]:
                self.proses(kunci, teks, self._epoch(), m["gerbang"])
                return
            if not cepat and jenis != "com":
                return                                   # ketikan manusia di keyboard biasa
            b = self.baru.setdefault(kunci, {"kunci": kunci, "jenis": jenis, "label": label,
                                             "tertahan": []})
            if len(b["tertahan"]) < 20:
                b["tertahan"].append((teks, self._epoch()))

    def petakan(self, kunci, gerbang_id=None, abaikan=False):
        with self.lock:
            info = self.baru.pop(kunci, None) or {"tertahan": []}
            lihat = self.terlihat.get(kunci, {})
            jenis = info.get("jenis") or lihat.get("jenis") or "keyboard"
            label = info.get("label") or lihat.get("label") or kunci
            if not abaikan and not self._nama_gerbang(gerbang_id):
                if info.get("kunci"):
                    self.baru[kunci] = info               # kembalikan: tetap menunggu dipilih
                return {"ok": False, "pesan": "Gerbang tidak dikenal"}
            self.peta_lokal[kunci] = {"gerbang_id": None if abaikan else gerbang_id,
                                      "abaikan": bool(abaikan), "jenis": jenis, "label": label,
                                      "terkirim": False}
            konfig.tulis("peta_lokal.json", self.peta_lokal)
            if not abaikan:
                for teks, ts in info.get("tertahan", []):
                    self.proses(kunci, teks, ts, self._nama_gerbang(gerbang_id))
        self._kirim_peta()
        return {"ok": True}

    def _kirim_peta(self):
        if not self.klien:
            return
        for kunci, p in list(self.peta_lokal.items()):
            if p.get("terkirim"):
                continue
            try:
                cfg = self.klien.petakan(kunci, p["jenis"], p["label"], p.get("gerbang_id"),
                                         p.get("abaikan", False))
            except (GalatJaringan, GalatServer):
                return
            with self.lock:
                self._terapkan_cfg(cfg)
                self.peta_lokal.pop(kunci, None)
                konfig.tulis("peta_lokal.json", self.peta_lokal)

    # ------------------------------------------------------------ proses scan
    def _foto(self, siswa_id):
        v = self.foto_versi.get(str(siswa_id))
        return f"/foto/{siswa_id}?v={v}" if v else None

    def _siswa_tampil(self, s):
        return {"nama": s["nama"], "kelas": s.get("kelas") or "", "foto": self._foto(s["id"])} if s else None

    def proses(self, kunci, teks, ts, gerbang):
        with self.lock:
            siswa, err, layak = self.data.cari(teks)
            jam = _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            if not layak:
                self._tambah_item({"gerbang": gerbang, "jam": jam, "level": "error", "jenis": "gagal",
                                   "pesan": err, "siswa": None})
                return None
            jeda = int(self.cfg.get("jeda_ganda") or 0)
            if siswa and jeda and ts - self._terakhir.get(siswa["id"], -10 ** 9) <= jeda:
                self._tambah_item({"gerbang": gerbang, "jam": jam, "level": "info", "jenis": "ganda",
                                   "pesan": "Scan ganda diabaikan", "siswa": self._siswa_tampil(siswa)})
                return None
            u = _uuid.uuid4().hex
            self.antrean.tambah(u, teks, kunci, ts)
            self.tertunda[u] = {"gerbang": gerbang, "jam": jam, "siswa": siswa, "ts": ts,
                                "t0": time.monotonic(), "selesai": False}
            if siswa:
                self._terakhir[siswa["id"]] = ts
        self._picu.set()
        return u

    def _hasil_server(self, h):
        with self.lock:
            d = self.tertunda.pop(h.get("uuid"), None)
            if d is None or d["selesai"]:
                return
            s = h.get("siswa") or {}
            lokal = d["siswa"]
            siswa = None
            if s or lokal:
                siswa = {"nama": s.get("nama") or (lokal or {}).get("nama"),
                         "kelas": s.get("kelas") or (lokal or {}).get("kelas") or "",
                         "foto": self._foto(s.get("id") or (lokal or {}).get("id"))}
            self._tambah_item({"gerbang": h.get("gerbang") or d["gerbang"],
                               "jam": (h.get("jam") or d["jam"])[:8], "level": h.get("level") or "info",
                               "jenis": h.get("jenis") or ("gagal" if not h.get("ok") else ""),
                               "status": h.get("status"), "pesan": h.get("pesan") or "",
                               "siswa": siswa})

    def _selesaikan_tertunda(self):
        """Server lambat/offline: tampilkan dari data lokal agar antrean siswa tetap lancar."""
        sekarang = time.monotonic()
        with self.lock:
            for u, d in list(self.tertunda.items()):
                if d["selesai"] or sekarang - d["t0"] < BATAS_TUNGGU:
                    continue
                d["selesai"] = True
                s = d["siswa"]
                self._tambah_item({"gerbang": d["gerbang"], "jam": d["jam"],
                                   "level": "success" if s else "warning", "jenis": "tersimpan",
                                   "pesan": "Tersimpan di PC — dikirim saat online" if s
                                   else "Belum dikenal di PC — diperiksa server saat online",
                                   "siswa": self._siswa_tampil(s)})
                if len(self.tertunda) > 2000:
                    self.tertunda.pop(u, None)

    def _tambah_item(self, it):
        hari = _dt.date.today()
        if self._tanggal != hari:
            self._tanggal, self._hadir = hari, {}
        self._id += 1
        it["id"] = self._id
        it["gerbang"] = it.get("gerbang") or ""
        if (it.get("jenis") in ("masuk", "tersimpan") and it.get("level") in ("success", "warning")
                and it.get("siswa")):
            self._hadir[it["gerbang"]] = self._hadir.get(it["gerbang"], 0) + 1
        self.item.append(it)
        del self.item[:-MAKS_ITEM]

    # ------------------------------------------------------------ umpan layar
    def umpan(self, sejak=None):
        with self.lock:
            if sejak is None:
                item = [dict(i, awal=True) for i in self.item[-60:]]
            else:
                item = [dict(i, awal=False) for i in self.item if i["id"] > sejak]
            nama = [g["nama"] for g in self.gerbang()]
            peringatan = self.peringatan
            if not self.terpasang:
                peringatan = "Pos belum dipasangkan dengan server sekolah"
            elif self.versi_baru and not peringatan:
                peringatan = f"Versi baru Presensiku Pos {self.versi_baru} tersedia — unduh dari menu Perangkat Scan"
            return {"sekolah": self.cfg.get("sekolah") or self.pos.get("sekolah") or "Presensiku Pos",
                    "gerbang": nama, "hadir": dict(self._hadir), "item": item,
                    "terakhir": self._id, "online": self.online,
                    "antrean": self.antrean.jumlah_belum(),
                    "baru": [{"kunci": b["kunci"], "label": b["label"], "jenis": b["jenis"]}
                             for b in self.baru.values()],
                    "pilihan_gerbang": [{"id": g["id"], "nama": g["nama"]} for g in self.gerbang()],
                    "peringatan": peringatan}

    # ------------------------------------------------------------ kirim & sinkron
    def kirim_sekali(self):
        if not self.klien:
            return 0
        batch = self.antrean.belum(50)
        if not batch:
            return 0
        try:
            hasil = self.klien.scan(batch)
        except GalatJaringan:
            self.online = False
            return -1
        except GalatServer as e:
            self.online = True
            if e.status == 402:
                self.peringatan = "Masa langganan sekolah habis — scan disimpan, dikirim setelah diperpanjang"
            elif e.status == 401:
                self.peringatan = "Pos ditolak server (dipasangkan ulang / dinonaktifkan). Hubungi admin."
            else:
                self.peringatan = f"Server menolak: {e}"
            return -1
        self.online = True
        self.peringatan = ""
        n = 0
        for h in hasil:
            if h.get("error") == "scanner":
                self._sinkron_sekarang.set()     # pemetaan belum sampai server; coba lagi nanti
                continue
            self.antrean.tandai(h["uuid"], h)
            self._hasil_server(h)
            n += 1
        return n

    def _terapkan_cfg(self, cfg):
        simpan = {k: cfg.get(k) for k in ("gerbang", "scanner", "qr_secret", "jeda_ganda", "sekolah",
                                          "pos")}
        self.cfg = simpan
        self.data.secret = simpan.get("qr_secret")
        konfig.tulis("server.json", simpan, rahasia=True)

    def sinkron(self):
        if not self.klien:
            return False
        try:
            self._kirim_peta()
            cfg = self.klien.sinkron(self.antrean.jumlah_belum(), list(self.terlihat.values()))
            with self.lock:
                self._terapkan_cfg(cfg)
            self.online = True
        except GalatJaringan:
            self.online = False
            return False
        except GalatServer as e:
            self.peringatan = f"Sinkron ditolak server: {e}"
            return False
        self._sinkron_siswa()
        self._cek_versi()
        return True

    def _sinkron_siswa(self, maks_foto=60):
        try:
            d = self.klien.siswa(self.data.versi)
        except (GalatJaringan, GalatServer):
            return
        if not d.get("sama"):
            with self.lock:
                konfig.tulis("siswa.json", d)
                self.data.isi(d)
        folder = konfig.jalur("foto")
        os.makedirs(folder, exist_ok=True)
        n = 0
        for s in list(self.data.siswa.values()):
            v = str(s.get("foto_versi") or 0)
            if not s.get("foto") or self.foto_versi.get(str(s["id"])) == v:
                continue
            try:
                isi = self.klien.foto(s["id"])
            except (GalatJaringan, GalatServer):
                break
            with open(os.path.join(folder, f"{s['id']}.jpg"), "wb") as f:
                f.write(isi)
            self.foto_versi[str(s["id"])] = v
            n += 1
            if n >= maks_foto:
                break
        if n:
            konfig.tulis("foto.json", self.foto_versi)

    def _cek_versi(self):
        try:
            from urllib.parse import urlsplit
            u = urlsplit(self.pos["server"])
            r = self.sesi.get(f"{u.scheme}://{u.netloc}/unduh/pos-versi.json", timeout=5) \
                if self.sesi else None
            if r is None:
                import requests
                r = requests.get(f"{u.scheme}://{u.netloc}/unduh/pos-versi.json", timeout=5)
            if r.status_code == 200:
                v = r.json().get("versi")
                self.versi_baru = v if v and _versi_tuple(v) > _versi_tuple(VERSI) else None
        except Exception:  # noqa: BLE001 — opsional
            pass

    # ------------------------------------------------------------ utas
    def _utas_kirim(self):
        jeda = 1
        while self.berjalan:
            self._picu.wait(timeout=3)
            self._picu.clear()
            while self.berjalan:
                n = self.kirim_sekali()
                if n == -1:
                    time.sleep(jeda)
                    jeda = min(jeda * 2, 30)
                    break
                jeda = 1
                if n == 0:
                    break

    def _utas_jam(self):
        while self.berjalan:
            time.sleep(0.1)
            with self.lock:
                for s in self.perakit.periksa_waktu():
                    info = self.terlihat.get(s.kunci, {})
                    self.terima(s.kunci, s.teks, s.cepat, "keyboard", info.get("label", s.kunci))
            self._selesaikan_tertunda()

    def _utas_sinkron(self):
        terakhir = 0
        while self.berjalan:
            self._sinkron_sekarang.wait(timeout=5)
            if self._sinkron_sekarang.is_set() or time.monotonic() - terakhir >= SINKRON_DETIK:
                self._sinkron_sekarang.clear()
                self.sinkron()
                terakhir = time.monotonic()
                self.antrean.bersihkan()

    def mulai(self):
        for f in (self._utas_kirim, self._utas_jam, self._utas_sinkron):
            threading.Thread(target=f, name=f.__name__, daemon=True).start()
        self._sinkron_sekarang.set()

    def berhenti(self):
        self.berjalan = False
        self._picu.set()
        self._sinkron_sekarang.set()
