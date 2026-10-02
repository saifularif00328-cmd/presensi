"""Pencocokan wajah di server (OpenCV YuNet + SFace, lisensi Apache-2.0).

- `analisis_gambar(bytes)` mengembalikan daftar wajah (kotak, skor, arah tengok/yaw,
  ketajaman, kecerahan, embedding 128 angka). Bila env PRESENSI_WAJAH_URL ada, analisis
  dikerjakan oleh satu proses bersama `presensi-wajah` (hemat RAM: model hanya dimuat sekali
  untuk semua sekolah); bila tidak, dikerjakan di proses ini (dimuat saat pertama dipakai).
- Data acuan (embedding) disimpan TERENKRIPSI di tabel wajah_siswa dan hanya boleh dibuat
  setelah ada persetujuan orang tua (UU PDP). Foto acuan tidak disimpan terpisah.
"""
import base64
import io
import os
import secrets
import threading

from .. import config, utils
from ..db import execute, get_setting, query

YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"
SISI_MAKS = 640                 # gambar diperkecil dulu: cepat & hemat RAM
LEBAR_MIN = 80                  # lebar wajah minimal (piksel, setelah diperkecil)
TAJAM_ACUAN = 30                # varians Laplacian minimal foto acuan; di bawah ini = buram
TAJAM_ABSEN = 10                # saat absen lebih longgar (SFace masih akurat untuk buram ringan)
TERANG = (45, 215)              # rata-rata kecerahan wajah yang wajar
YAW_LURUS = 0.22                # |yaw| maksimal untuk foto acuan "menghadap lurus"
YAW_TENGOK = 0.18               # perubahan yaw minimal saat tantangan tengok
MIRIP_SAMA = 0.30               # 2 frame absen harus wajah yang sama (yaw beda -> skor turun)


class TidakTersedia(Exception):
    """Mesin wajah belum terpasang (OpenCV / file model) atau layanan wajah mati."""


def model_dir():
    return os.environ.get("PRESENSI_MODEL_DIR") or os.path.join(config.BASE_DIR, "models")


# ------------------------------------------------------------------ mesin (dalam proses)
class Mesin:
    def __init__(self, folder=None):
        self.folder = folder or model_dir()
        self._lock = threading.Lock()
        self._det = self._rec = None

    def _muat(self):
        if self._det is not None:
            return
        try:
            import cv2  # noqa: F401
        except ImportError as e:
            raise TidakTersedia("Paket opencv-python-headless belum terpasang") from e
        import cv2
        for f in (YUNET, SFACE):
            if not os.path.exists(os.path.join(self.folder, f)):
                raise TidakTersedia(f"File model {f} tidak ada di {self.folder}")
        self._det = cv2.FaceDetectorYN.create(os.path.join(self.folder, YUNET), "", (320, 320), 0.75, 0.3, 50)
        self._rec = cv2.FaceRecognizerSF.create(os.path.join(self.folder, SFACE), "")

    def analisis(self, data):
        import cv2
        import numpy as np
        with self._lock:
            self._muat()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return {"ok": False, "pesan": "Berkas bukan gambar", "wajah": []}
            img = _putar_exif(data, img)
            h, w = img.shape[:2]
            skala = min(1.0, SISI_MAKS / max(h, w))
            if skala < 1:
                img = cv2.resize(img, (int(w * skala), int(h * skala)), interpolation=cv2.INTER_AREA)
                h, w = img.shape[:2]
            self._det.setInputSize((w, h))
            _, faces = self._det.detect(img)
            abu = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            hasil = []
            for f in ([] if faces is None else faces):
                x, y, fw, fh = (int(v) for v in f[:4])
                x0, y0 = max(0, x), max(0, y)
                potong = abu[y0:max(y0 + 1, y + fh), x0:max(x0 + 1, x + fw)]
                lm = f[4:14]
                jarak_mata = float(lm[2] - lm[0]) or 1.0
                yaw = float(lm[4] - (lm[0] + lm[2]) / 2) / jarak_mata
                emb = self._rec.feature(self._rec.alignCrop(img, f)).flatten()
                hasil.append({"kotak": [x, y, fw, fh], "skor": round(float(f[14]), 3),
                              "yaw": round(yaw, 3),
                              "tajam": round(float(cv2.Laplacian(potong, cv2.CV_64F).var()), 1),
                              "terang": round(float(potong.mean()), 1),
                              "embedding": [round(float(v), 6) for v in emb]})
            hasil.sort(key=lambda r: r["kotak"][2] * r["kotak"][3], reverse=True)
            return {"ok": True, "lebar": w, "tinggi": h, "wajah": hasil}


def _putar_exif(data, img):
    """Foto HP sering menyimpan arah di EXIF; luruskan agar wajah tidak miring 90°."""
    try:
        from PIL import Image
        o = Image.open(io.BytesIO(data)).getexif().get(0x0112)
    except Exception:  # noqa: BLE001
        return img
    import cv2
    putar = {3: cv2.ROTATE_180, 6: cv2.ROTATE_90_CLOCKWISE, 8: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(o)
    return cv2.rotate(img, putar) if putar is not None else img


_mesin = None


def _mesin_lokal():
    global _mesin
    if _mesin is None:
        _mesin = Mesin()
    return _mesin


def analisis_gambar(data):
    """Analisis satu gambar (bytes). Melempar TidakTersedia bila mesin tidak bisa dipakai."""
    url = os.environ.get("PRESENSI_WAJAH_URL")
    if not url:
        return _mesin_lokal().analisis(data)
    import requests
    try:
        r = requests.post(url.rstrip("/") + "/analisis", data=data, timeout=20,
                          headers={"X-Kunci": os.environ.get("PRESENSI_WAJAH_KUNCI", ""),
                                   "Content-Type": "application/octet-stream"})
    except requests.RequestException as e:
        raise TidakTersedia("Layanan wajah tidak menjawab") from e
    if r.status_code != 200:
        raise TidakTersedia(f"Layanan wajah error {r.status_code}")
    return r.json()


def status_mesin():
    """(siap, keterangan) untuk ditampilkan ke admin."""
    url = os.environ.get("PRESENSI_WAJAH_URL")
    if url:
        import requests
        try:
            r = requests.get(url.rstrip("/") + "/sehat", timeout=3)
            j = r.json()
            return bool(j.get("ok")), j.get("pesan") or "Layanan wajah bersama aktif"
        except Exception:  # noqa: BLE001
            return False, "Layanan wajah (presensi-wajah) tidak berjalan"
    try:
        _mesin_lokal()._muat()
        return True, "Mesin wajah siap (di proses aplikasi)"
    except TidakTersedia as e:
        return False, str(e)


# ------------------------------------------------------------------ kualitas & kemiripan
def wajah_utama(hasil, acuan=False):
    """(wajah, alasan_gagal). acuan=True memakai syarat foto acuan yang lebih ketat."""
    if not hasil.get("ok"):
        return None, hasil.get("pesan") or "Gambar tidak terbaca"
    daftar = hasil["wajah"]
    if not daftar:
        return None, "Wajah tidak terdeteksi"
    f = daftar[0]
    if len(daftar) > 1 and daftar[1]["kotak"][2] >= f["kotak"][2] * 0.6:
        return None, "Terlihat lebih dari satu wajah"
    if f["kotak"][2] < LEBAR_MIN:
        return None, "Wajah terlalu kecil / jauh dari kamera"
    if f["tajam"] < (TAJAM_ACUAN if acuan else TAJAM_ABSEN):
        return None, "Foto buram"
    if not TERANG[0] <= f["terang"] <= TERANG[1]:
        return None, "Foto terlalu gelap" if f["terang"] < TERANG[0] else "Foto terlalu terang"
    if acuan and abs(f["yaw"]) > YAW_LURUS:
        return None, "Wajah tidak menghadap lurus ke kamera"
    return f, ""


def kemiripan(a, b):
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def enkode(emb):
    import struct
    return utils.encrypt(base64.b64encode(struct.pack(f"<{len(emb)}f", *emb)).decode())


def dekode(teks):
    import struct
    raw = utils.decrypt(teks or "")
    if not raw:
        return None
    b = base64.b64decode(raw)
    return list(struct.unpack(f"<{len(b) // 4}f", b))


# ------------------------------------------------------------------ data acuan per siswa
def _fmt(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def data_siswa(siswa_id, db=None):
    return query("SELECT * FROM wajah_siswa WHERE siswa_id = ?", (siswa_id,), one=True, db=db)


def siap(siswa_id, db=None):
    r = data_siswa(siswa_id, db)
    return bool(r and r["setuju"] and r["status"] == "siap" and r["embedding"])


def catat_persetujuan(siswa_id, setuju, oleh, db=None):
    """Simpan persetujuan/pencabutan. Mencabut = data wajah langsung dihapus."""
    now = _fmt(utils.now())
    if setuju:
        execute("INSERT INTO wajah_siswa(siswa_id, setuju, setuju_oleh, setuju_waktu, status) "
                "VALUES (?,1,?,?,'kosong') ON DUPLICATE KEY UPDATE setuju = 1, setuju_oleh = VALUES(setuju_oleh), "
                "setuju_waktu = VALUES(setuju_waktu)", (siswa_id, oleh[:100], now), db=db)
    else:
        execute("INSERT INTO wajah_siswa(siswa_id, setuju, setuju_oleh, setuju_waktu, status) "
                "VALUES (?,0,?,?,'kosong') ON DUPLICATE KEY UPDATE setuju = 0, setuju_oleh = VALUES(setuju_oleh), "
                "setuju_waktu = VALUES(setuju_waktu), embedding = NULL, status = 'kosong', kualitas = NULL",
                (siswa_id, ("dicabut: " + oleh)[:100], now), db=db)


def daftarkan(siswa_id, data, sumber, db=None):
    """Buat data acuan dari satu foto (bytes). (ok, pesan)."""
    r = data_siswa(siswa_id, db)
    if not r or not r["setuju"]:
        return False, "Belum ada persetujuan orang tua"
    hasil = analisis_gambar(data)
    f, alasan = wajah_utama(hasil, acuan=True)
    now = _fmt(utils.now())
    if f is None:
        execute("UPDATE wajah_siswa SET status = 'ulang', kualitas = ?, diperbarui = ? WHERE siswa_id = ?",
                (alasan[:255], now, siswa_id), db=db)
        return False, alasan
    execute("UPDATE wajah_siswa SET embedding = ?, status = 'siap', sumber = ?, kualitas = ?, diperbarui = ? "
            "WHERE siswa_id = ?", (enkode(f["embedding"]), sumber[:10],
                                   f"tajam {f['tajam']:.0f} · lebar {f['kotak'][2]}px", now, siswa_id), db=db)
    return True, "Data wajah tersimpan"


def daftarkan_dari_foto(siswa_id, db=None):
    s = query("SELECT foto FROM siswa WHERE id = ?", (siswa_id,), one=True, db=db)
    if not s or not s["foto"]:
        return False, "Siswa belum punya foto"
    path = os.path.join(config.UPLOAD_DIR, s["foto"])
    if not os.path.exists(path):
        path = os.path.join(config.FOTO_DIR, os.path.basename(s["foto"]))
    try:
        with open(path, "rb") as fh:
            return daftarkan(siswa_id, fh.read(), "foto", db)
    except OSError:
        return False, "File foto siswa tidak ditemukan"


def hapus(siswa_id, db=None):
    execute("UPDATE wajah_siswa SET embedding = NULL, status = 'kosong', kualitas = NULL, diperbarui = ? "
            "WHERE siswa_id = ?", (_fmt(utils.now()), siswa_id), db=db)


# ------------------------------------------------------------------ verifikasi saat absen
def buat_tantangan():
    return secrets.choice(("kiri", "kanan"))


def verifikasi(siswa_id, foto1, foto2=None, tantangan=None, sumber="kamera", db=None):
    """Cocokkan foto absen dengan data acuan siswa.

    Mengembalikan dict: ok (lulus), skor, alasan (bila gagal), tipis (lulus tapi skor dekat ambang).
    Tantangan tengok: foto2 harus wajah yang sama dengan arah tengok sesuai. Foto kamera browser
    tidak dicerminkan, jadi tengok ke KIRI siswa = hidung bergeser ke KANAN gambar (yaw naik).
    Foto dari aplikasi kamera HP (sumber='berkas') kadang dicerminkan, jadi arah tidak dinilai,
    hanya besar perubahannya."""
    r = data_siswa(siswa_id, db)
    acuan = dekode(r["embedding"]) if r and r["setuju"] and r["status"] == "siap" else None
    if acuan is None:
        return {"ok": False, "skor": None, "alasan": "Data wajah siswa belum terdaftar"}
    ambang = float(get_setting("wajah_ambang", db=db) or 0.42)
    f1, alasan = wajah_utama(analisis_gambar(foto1))
    if f1 is None:
        return {"ok": False, "skor": None, "alasan": alasan}
    skor = round(kemiripan(f1["embedding"], acuan), 3)
    if skor < ambang:
        return {"ok": False, "skor": skor, "alasan": f"Wajah tidak cocok dengan data siswa (skor {skor:.2f})"}
    if tantangan:
        if not foto2:
            return {"ok": False, "skor": skor, "alasan": "Foto tantangan tengok tidak ada"}
        f2, alasan = wajah_utama(analisis_gambar(foto2))
        if f2 is None:
            return {"ok": False, "skor": skor, "alasan": f"Foto tengok: {alasan}"}
        if kemiripan(f1["embedding"], f2["embedding"]) < MIRIP_SAMA:
            return {"ok": False, "skor": skor, "alasan": "Wajah di dua foto berbeda"}
        geser = f2["yaw"] - f1["yaw"]
        if sumber == "berkas":
            benar = abs(geser) >= YAW_TENGOK
        else:
            benar = geser >= YAW_TENGOK if tantangan == "kiri" else geser <= -YAW_TENGOK
        if not benar:
            return {"ok": False, "skor": skor, "alasan": f"Tidak menengok ke {tantangan} (cek keaslian)"}
    return {"ok": True, "skor": skor, "tipis": skor < ambang + 0.08}

