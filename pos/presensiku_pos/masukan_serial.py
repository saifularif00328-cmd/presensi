"""Scanner mode COM (USB Virtual COM / serial): satu utas per port, satu baris = satu scan."""
import hashlib
import logging
import threading
import time

log = logging.getLogger(__name__)
BAUD = 9600


def kunci_port(info):
    """Kunci stabil dari nomor seri / VID:PID (nama COMx bisa berubah saat pindah port USB)."""
    dasar = (getattr(info, "serial_number", None) and
             f"{getattr(info, 'vid', '')}:{getattr(info, 'pid', '')}:{info.serial_number}") \
        or getattr(info, "hwid", "") or info.device
    return "COM-" + hashlib.sha1(str(dasar).upper().encode()).hexdigest()[:16]


def pecah_baris(sisa, data):
    """Gabungkan potongan bytes; kembalikan (baris_lengkap, sisa). Pemisah CR / LF / CRLF."""
    sisa += data
    baris = []
    while True:
        idx = min((i for i in (sisa.find(b"\r"), sisa.find(b"\n")) if i >= 0), default=-1)
        if idx < 0:
            break
        b, sisa = sisa[:idx], sisa[idx + 1:]
        t = b.decode("ascii", "ignore").strip()
        if t:
            baris.append(t)
    if len(sisa) > 512:          # tanpa akhiran baris: buang agar tidak membengkak
        sisa = b""
    return baris, sisa


class PembacaSerial:
    """Memantau semua port COM USB; panggil(kunci, label, teks) untuk setiap baris."""

    def __init__(self, panggil, daftar_port=None, buka=None, baud=BAUD):
        self.panggil = panggil
        self._daftar = daftar_port
        self._buka = buka
        self.baud = baud
        self.aktif = {}
        self.berjalan = True
        self.label = {}

    def _list(self):
        if self._daftar:
            return self._daftar()
        from serial.tools import list_ports
        # hanya port USB (abaikan COM bawaan motherboard / Bluetooth tanpa VID)
        return [p for p in list_ports.comports() if getattr(p, "vid", None)]

    def _open(self, device):
        if self._buka:
            return self._buka(device)
        import serial
        return serial.Serial(device, self.baud, timeout=0.2)

    def _baca(self, info, kunci, label):
        sisa = b""
        try:
            port = self._open(info.device)
        except Exception as e:  # noqa: BLE001 — port dipakai program lain / tidak bisa dibuka
            log.info("tidak bisa membuka %s: %s", info.device, e)
            time.sleep(5)
            self.aktif.pop(info.device, None)
            return
        log.info("membaca scanner COM %s (%s)", info.device, label)
        try:
            while self.berjalan:
                data = port.read(256)
                if not data:
                    continue
                baris, sisa = pecah_baris(sisa, data)
                for b in baris:
                    self.panggil(kunci, label, b)
        except Exception as e:  # noqa: BLE001 — kabel dicabut
            log.info("port %s terputus: %s", info.device, e)
        finally:
            try:
                port.close()
            except Exception:  # noqa: BLE001
                pass
            self.aktif.pop(info.device, None)

    def pindai(self):
        """Mulai utas untuk port baru. Mengembalikan daftar (kunci, label) yang terhubung."""
        for info in self._list():
            if info.device in self.aktif:
                continue
            kunci = kunci_port(info)
            label = f"{info.device} – {getattr(info, 'description', '') or 'scanner COM'}"[:150]
            self.label[kunci] = label
            t = threading.Thread(target=self._baca, args=(info, kunci, label),
                                 name=f"com-{info.device}", daemon=True)
            self.aktif[info.device] = (kunci, t)
            t.start()
        return [(k, self.label[k]) for k, _t in self.aktif.values()]

    def jalan(self, jeda=5):
        while self.berjalan:
            try:
                self.pindai()
            except Exception:  # noqa: BLE001
                log.exception("gagal memindai port COM")
            time.sleep(jeda)

    def mulai(self):
        t = threading.Thread(target=self.jalan, name="com-pindai", daemon=True)
        t.start()
        return t
