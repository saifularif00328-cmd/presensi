"""Membaca semua keyboard/scanner USB per alat lewat Windows Raw Input (khusus Windows).

Setiap ketikan membawa `hDevice` (alat asal). Jendela tersembunyi didaftarkan dengan
RIDEV_INPUTSINK sehingga ketikan scanner tetap diterima walau jendela Pos tidak sedang aktif.
Ketikan TIDAK dicegat (tetap juga sampai ke jendela aktif) — karena itu PC pos sebaiknya khusus
menampilkan Layar Gerbang (layar tersebut mengabaikan ketikan).
"""
import ctypes
import hashlib
import logging
import re
import threading
import time

log = logging.getLogger(__name__)

WM_INPUT = 0x00FF
WM_CLOSE = 0x0010
RID_INPUT = 0x10000003
RIDI_DEVICENAME = 0x20000007
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100
RIDEV_DEVNOTIFY = 0x00002000
RI_KEY_BREAK = 1

if hasattr(ctypes, "WinDLL"):          # hanya Windows
    from ctypes import wintypes as W

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", W.USHORT), ("usUsage", W.USHORT), ("dwFlags", W.DWORD),
                    ("hwndTarget", W.HWND)]

    class RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", W.DWORD), ("dwSize", W.DWORD), ("hDevice", W.HANDLE),
                    ("wParam", W.WPARAM)]

    class RAWKEYBOARD(ctypes.Structure):
        _fields_ = [("MakeCode", W.USHORT), ("Flags", W.USHORT), ("Reserved", W.USHORT),
                    ("VKey", W.USHORT), ("Message", W.UINT), ("ExtraInformation", W.ULONG)]

    class RAWINPUT(ctypes.Structure):
        _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]

    class RAWINPUTDEVICELIST(ctypes.Structure):
        _fields_ = [("hDevice", W.HANDLE), ("dwType", W.DWORD)]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                    ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                    ("lpszClassName", W.LPCWSTR)]

    user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = W.ATOM
    user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU,
                                       W.HINSTANCE, W.LPVOID]
    user32.CreateWindowExW.restype = W.HWND
    user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), W.UINT, W.UINT]
    user32.RegisterRawInputDevices.restype = W.BOOL
    user32.GetRawInputData.argtypes = [W.HANDLE, W.UINT, W.LPVOID, ctypes.POINTER(W.UINT), W.UINT]
    user32.GetRawInputData.restype = W.UINT
    user32.GetRawInputDeviceInfoW.argtypes = [W.HANDLE, W.UINT, W.LPVOID, ctypes.POINTER(W.UINT)]
    user32.GetRawInputDeviceInfoW.restype = W.UINT
    user32.GetRawInputDeviceList.argtypes = [ctypes.POINTER(RAWINPUTDEVICELIST),
                                             ctypes.POINTER(W.UINT), W.UINT]
    user32.GetRawInputDeviceList.restype = W.UINT
    user32.GetMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
    user32.GetMessageW.restype = W.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(W.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(W.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user32.DestroyWindow.argtypes = [W.HWND]
    kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]
    kernel32.GetModuleHandleW.restype = W.HMODULE


def nama_alat(hdev):
    """Jalur alat, mis. \\\\?\\HID#VID_1EAB&PID_1D06&MI_00#7&2a6d...#{884b...}."""
    n = W.UINT(0)
    user32.GetRawInputDeviceInfoW(hdev, RIDI_DEVICENAME, None, ctypes.byref(n))
    if not n.value:
        return ""
    buf = ctypes.create_unicode_buffer(n.value + 1)
    user32.GetRawInputDeviceInfoW(hdev, RIDI_DEVICENAME, buf, ctypes.byref(n))
    return buf.value


def kunci_dan_label(jalur):
    """Kunci stabil (sama setelah PC dinyalakan ulang, selama dicolok di port USB yang sama)."""
    bersih = re.sub(r"#\{[0-9a-fA-F-]+\}$", "", jalur or "").upper()
    kunci = "KB-" + hashlib.sha1(bersih.encode()).hexdigest()[:16]
    m = re.search(r"VID_([0-9A-F]{4}).*?PID_([0-9A-F]{4})", bersih)
    if m:
        label = f"USB VID {m.group(1)} PID {m.group(2)}"
    else:   # mis. \\?\ROOT#RDP_KBD#0000#{...} (keyboard virtual / bawaan)
        tanpa_awalan = re.sub(r"^\\\\\?\\", "", re.sub(r"\{[^}]*\}", "", bersih))
        bagian = [b for b in tanpa_awalan.split("#") if b]
        label = f"Keyboard {bagian[1] if len(bagian) > 1 else (bagian[0] if bagian else 'tanpa nama')}"
    return kunci, label


def daftar_alat():
    """Semua keyboard/scanner yang terpasang: [(kunci, label)]."""
    n = W.UINT(0)
    user32.GetRawInputDeviceList(None, ctypes.byref(n), ctypes.sizeof(RAWINPUTDEVICELIST))
    arr = (RAWINPUTDEVICELIST * n.value)()
    user32.GetRawInputDeviceList(arr, ctypes.byref(n), ctypes.sizeof(RAWINPUTDEVICELIST))
    hasil = {}
    for d in arr[:n.value]:
        if d.dwType == RIM_TYPEKEYBOARD:
            jalur = nama_alat(d.hDevice)
            if jalur:
                k, label = kunci_dan_label(jalur)
                hasil[k] = label
    return sorted(hasil.items())


class PembacaRawInput:
    """Utas pesan Windows yang meneruskan setiap tombol: panggil(kunci, label, vk, turun, waktu)."""

    def __init__(self, panggil, terima_virtual=False):
        self.panggil = panggil
        self.terima_virtual = terima_virtual   # uji otomatis: SendInput memakai hDevice = 0
        self._cache = {}
        self.hwnd = None
        self.siap = threading.Event()
        self.galat = None

    def _alat(self, hdev):
        if hdev not in self._cache:
            self._cache[hdev] = kunci_dan_label(nama_alat(hdev))
        return self._cache[hdev]

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            try:
                self._olah(lparam)
            except Exception:  # noqa: BLE001 — jangan sampai utas pesan mati
                log.exception("gagal membaca raw input")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _olah(self, lparam):
        n = W.UINT(ctypes.sizeof(RAWINPUT))
        ri = RAWINPUT()
        hasil = user32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(ri), ctypes.byref(n),
                                       ctypes.sizeof(RAWINPUTHEADER))
        if hasil == 0xFFFFFFFF or ri.header.dwType != RIM_TYPEKEYBOARD:
            return
        hdev = ri.header.hDevice
        if not hdev:
            if not self.terima_virtual:
                return                       # ketikan buatan program (bukan alat fisik)
            kunci, label = "KB-VIRTUAL", "keyboard virtual (uji)"
        else:
            kunci, label = self._alat(hdev)
        turun = not (ri.keyboard.Flags & RI_KEY_BREAK)
        self.panggil(kunci, label, ri.keyboard.VKey, turun, time.monotonic())

    def jalan(self):
        try:
            self._proc = WNDPROC(self._wndproc)       # simpan referensi agar tidak dibuang GC
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = "PresensikuPosRawInput"
            user32.RegisterClassW(ctypes.byref(wc))
            self.hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "Presensiku Pos", 0, 0, 0, 0, 0,
                                               None, None, hinst, None)
            if not self.hwnd:
                raise OSError(ctypes.get_last_error(), "CreateWindowExW gagal")
            rid = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK | RIDEV_DEVNOTIFY, self.hwnd)
            if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)):
                raise OSError(ctypes.get_last_error(), "RegisterRawInputDevices gagal")
        except Exception as e:  # noqa: BLE001
            self.galat = e
            self.siap.set()
            log.exception("Raw Input tidak bisa dimulai")
            return
        self.siap.set()
        msg = W.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def mulai(self):
        t = threading.Thread(target=self.jalan, name="raw-input", daemon=True)
        t.start()
        self.siap.wait(5)
        if self.galat:
            raise self.galat
        return t

    def berhenti(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
