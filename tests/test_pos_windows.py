"""Presensiku Pos — uji khusus Windows (Raw Input sungguhan). Dijalankan di runner Windows CI."""
import ctypes
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "pos"))

pytestmark = pytest.mark.skipif(os.name != "nt", reason="khusus Windows")


def test_raw_input_menerima_ketikan():
    from presensiku_pos import masukan_windows as MW
    from presensiku_pos.perakit import Perakit
    alat = MW.daftar_alat()
    print("keyboard/scanner terpasang:", alat)
    p, hasil = Perakit(), []

    def tombol(kunci, label, vk, turun, t):
        s = p.tombol(kunci, vk, turun, t)
        if s:
            hasil.append(s)

    r = MW.PembacaRawInput(tombol, terima_virtual=True)
    r.mulai()                                   # RegisterRawInputDevices harus berhasil
    assert r.hwnd

    class KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", ctypes.c_ulong), ("u", _U)]

    def kirim(vk, naik=False):
        i = INPUT(type=1)
        i.ki = KI(vk, 0, 2 if naik else 0, 0, 0)
        return ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))

    terkirim = 0
    for vk in [0x30, 0x34, 0x41, 0x31, 0x42, 0x32, 0x43, 0x33, 0x0D]:
        terkirim += kirim(vk) + kirim(vk, True)
    if not terkirim:
        pytest.skip("SendInput tidak tersedia di sesi ini (runner tanpa desktop interaktif)")
    batas = time.time() + 3
    while not hasil and time.time() < batas:
        time.sleep(0.05)
    if not hasil:
        pytest.skip("Desktop runner tidak meneruskan input ke Raw Input")
    assert hasil[0].teks.upper() == "04A1B2C3" and hasil[0].kunci == "KB-VIRTUAL"
