"""Terjemahan kode tombol Windows (Virtual-Key) dari scanner mode keyboard menjadi karakter.

Scanner mengetik isi QR/UID sebagai tombol keyboard US. Isi kartu presensi hanya memakai huruf,
angka, titik, dan tanda minus, sehingga tabel sederhana ini cukup dan tidak bergantung pada tata
letak keyboard Windows yang sedang aktif.
"""
SHIFT = {0x10, 0xA0, 0xA1}
AKHIR = {0x0D, 0x09}                  # Enter / Tab (akhiran scan)

_ANGKA_SHIFT = ")!@#$%^&*("
_OEM = {0xBA: (";", ":"), 0xBB: ("=", "+"), 0xBC: (",", "<"), 0xBD: ("-", "_"), 0xBE: (".", ">"),
        0xBF: ("/", "?"), 0xC0: ("`", "~"), 0xDB: ("[", "{"), 0xDC: ("\\", "|"), 0xDD: ("]", "}"),
        0xDE: ("'", '"'), 0x20: (" ", " ")}
_NUMPAD = {0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".", 0x6F: "/"}


def karakter(vk, shift=False):
    """Karakter untuk satu tombol, atau None bila bukan tombol karakter."""
    if 0x30 <= vk <= 0x39:
        return _ANGKA_SHIFT[vk - 0x30] if shift else chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk) if shift else chr(vk).lower()
    if 0x60 <= vk <= 0x69:
        return chr(vk - 0x60 + 0x30)
    if vk in _NUMPAD:
        return _NUMPAD[vk]
    if vk in _OEM:
        return _OEM[vk][1 if shift else 0]
    return None
