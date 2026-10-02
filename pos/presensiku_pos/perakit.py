"""Merakit ketikan per alat menjadi satu hasil scan.

Windows Raw Input memberi tahu alat asal setiap tombol, jadi ketikan dari beberapa scanner yang
datang bersamaan tetap terpisah per alat. Dari pola waktunya, ketikan scanner (sangat cepat,
< ±40 ms per karakter) dibedakan dari ketikan manusia di keyboard biasa.
"""
import time
from dataclasses import dataclass, field

from . import vk as VK

JEDA_RESET = 0.5        # jeda antartombol lebih lama dari ini = mulai rangkaian baru
CEPAT_MAKS = 0.045      # rata-rata jeda antarkarakter maksimal untuk dianggap scanner
MIN_PANJANG = 4
SELESAI_TANPA_ENTER = 0.15   # scanner tanpa akhiran Enter: rangkaian cepat dianggap selesai


@dataclass
class Scan:
    kunci: str
    teks: str
    cepat: bool
    waktu: float


@dataclass
class _Buffer:
    teks: list = field(default_factory=list)
    waktu: list = field(default_factory=list)
    shift: bool = False


class Perakit:
    def __init__(self):
        self.buf = {}

    def _b(self, kunci):
        if kunci not in self.buf:
            self.buf[kunci] = _Buffer()
        return self.buf[kunci]

    @staticmethod
    def _cepat(waktu):
        if len(waktu) < MIN_PANJANG:
            return False
        jeda = [b - a for a, b in zip(waktu, waktu[1:])]
        return sum(jeda) / len(jeda) <= CEPAT_MAKS

    def _selesai(self, kunci, b, t):
        teks = "".join(b.teks).strip()
        cepat = self._cepat(b.waktu)
        b.teks, b.waktu = [], []
        if not teks:
            return None
        return Scan(kunci, teks, cepat, t)

    def tombol(self, kunci, vk, turun, t=None):
        """Satu kejadian tombol dari alat `kunci`. Mengembalikan Scan bila rangkaian selesai."""
        t = time.monotonic() if t is None else t
        b = self._b(kunci)
        if vk in VK.SHIFT:
            b.shift = turun
            return None
        if not turun:
            return None
        if vk in VK.AKHIR:
            return self._selesai(kunci, b, t)
        ch = VK.karakter(vk, b.shift)
        if ch is None:
            return None
        if b.waktu and t - b.waktu[-1] > JEDA_RESET:
            b.teks, b.waktu = [], []
        b.teks.append(ch)
        b.waktu.append(t)
        return None

    def teks(self, kunci, teks, t=None):
        """Masukan yang sudah berupa teks per baris (scanner mode COM)."""
        t = time.monotonic() if t is None else t
        teks = (teks or "").strip()
        return Scan(kunci, teks, True, t) if teks else None

    def periksa_waktu(self, t=None):
        """Scanner tanpa akhiran Enter: rangkaian cepat yang berhenti dianggap selesai."""
        t = time.monotonic() if t is None else t
        hasil = []
        for kunci, b in self.buf.items():
            if b.waktu and t - b.waktu[-1] >= SELESAI_TANPA_ENTER:
                if self._cepat(b.waktu) and len(b.teks) >= 6:
                    s = self._selesai(kunci, b, t)
                    if s:
                        hasil.append(s)
                elif t - b.waktu[-1] > JEDA_RESET:
                    b.teks, b.waktu = [], []
        return hasil
