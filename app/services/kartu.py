"""Kartu pelajar ber-QR: 5 template × 2 orientasi (horizontal / vertikal), warna bisa dipilih.

Ukuran kartu mengikuti standar ID card CR80 (85,6 × 54 mm). PDF berisi grid kartu
siap cetak pada kertas A4: horizontal 2 × 5, vertikal 3 × 3 per halaman.
"""
import io
import os

from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .. import config
from ..qr import make_payload, qr_png

# ------------------------------------------------------------------ pilihan
TEMPLATES = {
    "modern": ("Modern", "Panel miring berwarna dengan foto bulat"),
    "klasik": ("Klasik", "Header berwarna penuh, rapi dan formal"),
    "minimal": ("Minimal", "Putih bersih dengan aksen garis tipis"),
    "elegan": ("Elegan", "Latar gelap dengan aksen warna, kesan premium"),
    "gradien": ("Gradien", "Latar gradasi warna penuh, tampilan dinamis"),
}
ORIENTASI = {"h": "Horizontal", "v": "Vertikal"}
WARNA = {
    "biru": ("Biru", "#1d4ed8"),
    "navy": ("Navy", "#1e3a8a"),
    "hijau": ("Hijau", "#047857"),
    "tosca": ("Tosca", "#0f766e"),
    "merah": ("Merah Marun", "#9f1239"),
    "ungu": ("Ungu", "#6d28d9"),
    "oranye": ("Oranye", "#c2410c"),
    "emas": ("Emas", "#a16207"),
}
DEFAULT = {"template": "modern", "orientasi": "h", "warna": "biru"}

CARD_LONG, CARD_SHORT = 85.6, 54.0  # mm
PT = 25.4 / 72  # 1 pt dalam mm (kartu digambar dalam satuan mm, ukuran font dalam pt)

# ------------------------------------------------------------------ font
_FONT_DIR = os.path.join(config.BUNDLE_DIR, "fonts")
F = {"r": "Helvetica", "m": "Helvetica", "sb": "Helvetica-Bold", "b": "Helvetica-Bold"}


def _register_fonts():
    try:
        for key, name in (("r", "Regular"), ("m", "Medium"), ("sb", "SemiBold"), ("b", "Bold")):
            font = f"Inter-{name}"
            if font not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font, os.path.join(_FONT_DIR, f"{font}.ttf")))
            F[key] = font
    except Exception:  # font tidak ada → pakai Helvetica bawaan
        pass


_register_fonts()


# ------------------------------------------------------------------ warna
def _mix(c1, c2, t):
    return colors.Color(c1.red + (c2.red - c1.red) * t, c1.green + (c2.green - c1.green) * t,
                        c1.blue + (c2.blue - c1.blue) * t)


WHITE = colors.white
INK = colors.HexColor("#101828")
GREY = colors.HexColor("#667085")
LINE = colors.HexColor("#e4e7ec")
DARK_BG = colors.HexColor("#0b1220")


class Ctx:
    """Data bersama untuk menggambar satu kartu."""

    def __init__(self, s, sekolah, alamat, logo, accent_hex, db):
        self.s = s
        self.sekolah = sekolah or ""
        self.alamat = alamat or ""
        self.logo = logo
        self.accent = colors.HexColor(accent_hex)
        self.dark = _mix(self.accent, colors.black, .35)
        self.soft = _mix(self.accent, WHITE, .88)
        self.light = _mix(self.accent, WHITE, .55)
        self.qr = ImageReader(qr_png(make_payload(s["qr_token"], db=db), box_size=8, border=0))
        self.foto = _load_foto(s["foto"])

    @property
    def nama(self):
        return self.s["nama"] or ""

    @property
    def kelas(self):
        return self.s["kelas_nama"] or "-"

    @property
    def nis(self):
        return self.s["nis"] or "-"

    @property
    def nisn(self):
        return self.s["nisn"] or "-"


def _load_foto(rel):
    """Foto dipotong ke rasio 3:4 (cover) agar tidak gepeng."""
    if not rel:
        return None
    path = os.path.join(config.UPLOAD_DIR, rel)
    if not os.path.exists(path):
        return None
    try:
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        img = ImageOps.fit(img, (450, 600), Image.LANCZOS, centering=(0.5, 0.35))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        buf.seek(0)
        return img, ImageReader(buf)
    except Exception:
        return None


# ------------------------------------------------------------------ helper gambar
def _sw(txt, font, size):
    """Lebar teks (mm) untuk ukuran font `size` pt."""
    return pdfmetrics.stringWidth(txt, font, size) * PT


def _rrect_path(c, x, y, w, h, r):
    p = c.beginPath()
    p.roundRect(x, y, w, h, r)
    return p


def _text(c, txt, x, y, font, size, color, align="l", spacing=0):
    c.setFillColor(color)
    c.setFont(font, size * PT)
    if spacing:
        width = _sw(txt, font, size) + spacing * (len(txt) - 1)
        if align == "c":
            x -= width / 2
        elif align == "r":
            x -= width
        t = c.beginText(x, y)
        t.setFont(font, size * PT)
        t.setCharSpace(spacing)
        t.setFillColor(color)
        t.textOut(txt)
        t.setCharSpace(0)  # operator Tc bertahan di luar BT/ET → wajib di-reset
        c.drawText(t)
        return
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[align](x, y, txt)


def _fit(txt, font, size, max_w, min_size):
    while size > min_size and _sw(txt, font, size) > max_w:
        size -= .25
    return size


def _text_fit(c, txt, x, y, max_w, font, size, color, align="l", min_size=5):
    _text(c, txt, x, y, font, _fit(txt, font, size, max_w, min_size), color, align)


def _name(c, txt, x, y, max_w, size, color, align="l", font=None, min_size=7):
    """Nama siswa: diperkecil bila panjang; bila tetap tidak muat, dipecah 2 baris
    (baris pertama naik) sehingga baseline baris terakhir tetap di `y`."""
    font = font or F["b"]
    s = _fit(txt, font, size, max_w, min_size)
    if _sw(txt, font, s) <= max_w:
        _text(c, txt, x, y, font, s, color, align)
        return 1
    s = _fit(txt, font, size, max_w * 2, min_size)
    lines = simpleSplit(txt, font, s, max_w / PT)[:2]
    for i, line in enumerate(lines):
        _text(c, line, x, y + (len(lines) - 1 - i) * s * PT * 1.15, font, s, color, align)
    return len(lines)


def _name_extra(txt, max_w, size, min_size=7, font=None):
    """Tinggi tambahan (mm) bila nama perlu 2 baris — dipakai untuk mengecilkan foto."""
    font = font or F["b"]
    s = _fit(txt, font, size, max_w, min_size)
    if _sw(txt, font, s) <= max_w:
        return 0
    s = _fit(txt, font, size, max_w * 2, min_size)
    return s * PT * 1.15 if len(simpleSplit(txt, font, s, max_w / PT)) > 1 else 0


def _photo(c, k, x, y, w, h, r=1.8, circle=False, ring=None, ring_w=.9):
    """Foto siswa (atau placeholder siluet) dengan sudut membulat / lingkaran."""
    c.saveState()
    if ring is not None:
        c.setFillColor(ring)
        if circle:
            c.circle(x + w / 2, y + h / 2, w / 2 + ring_w, stroke=0, fill=1)
        else:
            c.roundRect(x - ring_w, y - ring_w, w + 2 * ring_w, h + 2 * ring_w, r + ring_w, stroke=0,
                        fill=1)
    p = c.beginPath()
    if circle:
        p.circle(x + w / 2, y + h / 2, w / 2)
    else:
        p.roundRect(x, y, w, h, r)
    c.clipPath(p, stroke=0, fill=0)
    if k.foto:
        img, reader = k.foto
        iw, ih = img.size
        # cover: isi kotak penuh, potong kelebihan
        scale = max(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        c.drawImage(reader, x + (w - dw) / 2, y + (h - dh) / 2 - (dh - h) * .15, dw, dh)
    else:
        c.setFillColor(k.soft)
        c.rect(x, y, w, h, stroke=0, fill=1)
        c.setFillColor(k.light)
        cx = x + w / 2
        c.circle(cx, y + h * .60, min(w, h) * .19, stroke=0, fill=1)
        c.ellipse(cx - w * .36, y - h * .18, cx + w * .36, y + h * .40, stroke=0, fill=1)
    c.restoreState()


def _qr(c, k, x, y, size, pad=1.4, bg=WHITE, radius=1.6, border=None):
    c.setFillColor(bg)
    if border is not None:
        c.setStrokeColor(border)
        c.setLineWidth(.4)
    c.roundRect(x - pad, y - pad, size + 2 * pad, size + 2 * pad, radius,
                stroke=1 if border is not None else 0, fill=1)
    c.drawImage(k.qr, x, y, size, size)


def _initials(nama):
    words = [w for w in nama.replace(".", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:3]).upper() or "S"


def _logo(c, k, cx, cy, r, bg=WHITE, fg=None):
    """Logo sekolah (bila diunggah) atau monogram inisial sekolah."""
    fg = fg or k.accent
    c.saveState()
    c.setFillColor(bg)
    c.circle(cx, cy, r, stroke=0, fill=1)
    if k.logo:
        try:
            s = r * 1.55
            c.drawImage(ImageReader(k.logo), cx - s / 2, cy - s / 2, s, s,
                        preserveAspectRatio=True, anchor="c", mask="auto")
            c.restoreState()
            return
        except Exception:
            pass
    ini = _initials(k.sekolah)
    size = _fit(ini, F["b"], r * 1.05 / PT, r * 1.5, 3)
    _text(c, ini, cx, cy - size * PT * .36, F["b"], size, fg, "c")
    c.restoreState()


def _clip_card(c, w, h, r=3.2):
    c.clipPath(_rrect_path(c, 0, 0, w, h, r), stroke=0, fill=0)


def _outline(c, w, h, r=3.2):
    c.setStrokeColor(colors.HexColor("#d0d5dd"))
    c.setLineWidth(.35)
    c.roundRect(0, 0, w, h, r, stroke=1, fill=0)


def _label_value(c, label, value, x, y, lab_color, val_color, max_w, size=7.2):
    _text(c, label.upper(), x, y + 3.1, F["sb"], 4.6, lab_color, spacing=.35)
    _text_fit(c, value, x, y - .2, max_w, F["sb"], size, val_color)


# =================================================================== TEMPLATES
# Semua fungsi menggambar dalam satuan mm dengan origin di pojok kiri-bawah kartu.

def t_modern(c, k, W, H, hor):
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    if hor:
        # panel miring + lapisan dekoratif
        c.setFillColor(k.soft)
        p = c.beginPath(); p.moveTo(0, 0); p.lineTo(36, 0); p.lineTo(28, H); p.lineTo(0, H); p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(k.accent)
        p = c.beginPath(); p.moveTo(0, 0); p.lineTo(31, 0); p.lineTo(23, H); p.lineTo(0, H); p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(k.dark); c.setFillAlpha(.35)
        p = c.beginPath(); p.moveTo(0, 0); p.lineTo(18, 0); p.lineTo(0, 22); p.close()
        c.drawPath(p, stroke=0, fill=1); c.setFillAlpha(1)
        _logo(c, k, 7, H - 7, 3.6)
        _photo(c, k, 7.5, 13.5, 22, 22, circle=True, ring=WHITE, ring_w=1.1)
        tx = 36
        _text_fit(c, k.sekolah.upper(), tx, H - 7.2, W - tx - 4, F["b"], 6.4, k.accent, min_size=4.2)
        _text(c, "KARTU PELAJAR", tx, H - 10.6, F["sb"], 4.6, GREY, spacing=.55)
        c.setFillColor(k.accent); c.rect(tx, H - 12.6, 7, .55, stroke=0, fill=1)
        _name(c, k.nama, tx, 33.5, W - tx - 4, 10, INK, min_size=7)
        # pill kelas
        kel = f"Kelas {k.kelas}"
        pw = _sw(kel, F["sb"], 6.2) + 4.4
        c.setFillColor(k.soft); c.roundRect(tx, 26.2, pw, 4.4, 2.2, stroke=0, fill=1)
        _text(c, kel, tx + 2.2, 27.6, F["sb"], 6.2, k.accent)
        _label_value(c, "NIS", k.nis, tx, 19.2, GREY, INK, 20)
        _label_value(c, "NISN", k.nisn, tx, 11.6, GREY, INK, 20)
        _qr(c, k, W - 4.6 - 19, 5.2, 19, border=LINE)
        _text(c, "Pindai untuk presensi", W - 4.6 - 9.5, 2.1, F["m"], 3.9, GREY, "c")
    else:
        c.setFillColor(k.soft)
        p = c.beginPath(); p.moveTo(0, H); p.lineTo(W, H); p.lineTo(W, H - 27); p.lineTo(0, H - 36); p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(k.accent)
        p = c.beginPath(); p.moveTo(0, H); p.lineTo(W, H); p.lineTo(W, H - 23); p.lineTo(0, H - 32); p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(k.dark); c.setFillAlpha(.35)
        p = c.beginPath(); p.moveTo(W, H); p.lineTo(W, H - 23); p.lineTo(W - 26, H); p.close()
        c.drawPath(p, stroke=0, fill=1); c.setFillAlpha(1)
        _logo(c, k, W / 2, H - 6.8, 3.4)
        _text_fit(c, k.sekolah.upper(), W / 2, H - 13.6, W - 8, F["b"], 5.8, WHITE, "c", 4)
        _text(c, "KARTU PELAJAR", W / 2, H - 16.9, F["sb"], 4.3, k.light, "c", spacing=.5)
        ex = _name_extra(k.nama, W - 8, 9.2, 6.5)
        d = 23 - ex
        _photo(c, k, W / 2 - d / 2, H - 22.5 - d, d, d, circle=True, ring=WHITE, ring_w=1.1)
        _name(c, k.nama, W / 2, 34.2, W - 8, 9.2, INK, "c", min_size=6.5)
        kel = f"Kelas {k.kelas}"
        pw = _sw(kel, F["sb"], 5.8) + 4
        c.setFillColor(k.soft); c.roundRect(W / 2 - pw / 2, 28.3, pw, 4.1, 2.05, stroke=0, fill=1)
        _text(c, kel, W / 2, 29.6, F["sb"], 5.8, k.accent, "c")
        _text_fit(c, f"NIS {k.nis}  ·  NISN {k.nisn}", W / 2, 24.6, W - 8, F["m"], 5.4, GREY, "c", 4)
        _qr(c, k, W / 2 - 8.5, 4.4, 17, border=LINE)
        c.setFillColor(k.accent); c.rect(0, 0, W, 1.4, stroke=0, fill=1)


def t_klasik(c, k, W, H, hor):
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    if hor:
        c.setFillColor(k.accent); c.rect(0, H - 13, W, 13, stroke=0, fill=1)
        c.setFillColor(k.dark); c.rect(0, H - 13.9, W, .9, stroke=0, fill=1)
        _logo(c, k, 7.6, H - 6.5, 4.3)
        _text_fit(c, k.sekolah.upper(), 14, H - 6, W - 18, F["b"], 7, WHITE, min_size=4.5)
        _text(c, "KARTU TANDA PELAJAR", 14, H - 9.9, F["m"], 4.6, k.light, spacing=.45)
        _photo(c, k, 5, 8.5, 20, 26, r=1.4, ring=LINE, ring_w=.35)
        tx = 29
        _name(c, k.nama, tx, 33.5, W - tx - 4, 9, INK, min_size=6.8)
        c.setStrokeColor(LINE); c.setLineWidth(.35); c.line(tx, 31.2, W - 28, 31.2)
        rows = (("Kelas", k.kelas), ("NIS", k.nis), ("NISN", k.nisn))
        for i, (lab, val) in enumerate(rows):
            yy = 27 - i * 5.3
            _text(c, lab, tx, yy, F["m"], 5.6, GREY)
            _text(c, ":", tx + 9, yy, F["m"], 5.6, GREY)
            _text_fit(c, val, tx + 10.5, yy, 17, F["sb"], 6.2, INK)
        _qr(c, k, W - 4.5 - 21, 7.6, 21, border=LINE)
        c.setFillColor(k.accent); c.rect(0, 0, W, 4.2, stroke=0, fill=1)
        _text_fit(c, k.alamat, W / 2, 1.5, W - 8, F["r"], 4, WHITE, "c", 3)
    else:
        c.setFillColor(k.accent); c.rect(0, H - 20, W, 20, stroke=0, fill=1)
        c.setFillColor(k.dark); c.rect(0, H - 20.9, W, .9, stroke=0, fill=1)
        _logo(c, k, W / 2, H - 7, 4.2)
        _text_fit(c, k.sekolah.upper(), W / 2, H - 14.3, W - 6, F["b"], 6.2, WHITE, "c", 4)
        _text(c, "KARTU TANDA PELAJAR", W / 2, H - 17.8, F["m"], 4.2, k.light, "c", spacing=.4)
        ex = _name_extra(k.nama, W - 7, 8.6, 6.2)
        ph = 27 - ex
        _photo(c, k, W / 2 - ph * 21 / 54, H - 24 - ph, ph * 21 / 27, ph, r=1.4, ring=LINE, ring_w=.35)
        _name(c, k.nama, W / 2, 30.2, W - 7, 8.6, INK, "c", min_size=6.2)
        _text_fit(c, f"Kelas {k.kelas}  ·  NIS {k.nis}", W / 2, 26.1, W - 7, F["m"], 5.6, GREY, "c", 4)
        _qr(c, k, W / 2 - 9, 5.6, 18, border=LINE)
        c.setFillColor(k.accent); c.rect(0, 0, W, 3.2, stroke=0, fill=1)
        _text_fit(c, k.alamat, W / 2, 1.1, W - 6, F["r"], 3.6, WHITE, "c", 2.8)


def t_minimal(c, k, W, H, hor):
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    if hor:
        c.setFillColor(k.accent); c.rect(0, 0, 2.2, H, stroke=0, fill=1)
        _logo(c, k, 9, H - 7, 3.1, bg=k.soft)
        _text_fit(c, k.sekolah, 14, H - 8, 40, F["b"], 6.8, INK, min_size=4.5)
        _text(c, "KARTU PELAJAR", W - 4.5, H - 8, F["sb"], 4.6, k.accent, "r", spacing=.5)
        c.setStrokeColor(LINE); c.setLineWidth(.4); c.line(6, H - 12, W - 4.5, H - 12)
        _photo(c, k, 6, 6, 19, 25, r=1.6)
        tx = 29
        _name(c, k.nama, tx, 35.8, W - tx - 4.5, 9.4, INK, min_size=6.8)
        _label_value(c, "Kelas", k.kelas, tx, 24.6, GREY, INK, 14)
        _label_value(c, "NIS", k.nis, tx + 15, 24.6, GREY, INK, 13)
        _label_value(c, "NISN", k.nisn, tx, 14.4, GREY, INK, 26)
        _qr(c, k, W - 4.5 - 20, 6, 20, pad=0)
        _text(c, "SCAN PRESENSI", W - 4.5 - 10, 3.2, F["sb"], 3.7, GREY, "c", spacing=.35)
        _outline(c, W, H)
    else:
        c.setFillColor(k.accent); c.rect(0, H - 2.2, W, 2.2, stroke=0, fill=1)
        _logo(c, k, 8, H - 8.6, 3, bg=k.soft)
        _text_fit(c, k.sekolah, 12.8, H - 9.6, W - 17, F["b"], 6.2, INK, min_size=4)
        _text(c, "KARTU PELAJAR", 5, H - 15.2, F["sb"], 4.3, k.accent, spacing=.5)
        ex = _name_extra(k.nama, W - 10, 8.8, 6.3)
        _photo(c, k, 5, H - 45 + ex, 20 - ex * 20 / 26, 26 - ex, r=1.6)
        tx = 28.5
        _label_value(c, "Kelas", k.kelas, tx, H - 24, GREY, INK, W - tx - 4)
        _label_value(c, "NIS", k.nis, tx, H - 32, GREY, INK, W - tx - 4)
        _label_value(c, "NISN", k.nisn, tx, H - 40, GREY, INK, W - tx - 4)
        c.setStrokeColor(LINE); c.setLineWidth(.4); c.line(5, H - 48.5 + ex, W - 5, H - 48.5 + ex)
        _name(c, k.nama, 5, 31.3, W - 10, 8.8, INK, min_size=6.3)
        _qr(c, k, 5, 5, 20, pad=0)
        for i, line in enumerate(("Pindai QR ini", "untuk presensi", "masuk & pulang")):
            _text(c, line, 28.5, 19 - i * 3.6, F["m"], 4.6, GREY)
        c.setFillColor(k.accent); c.rect(28.5, 7, 6, .6, stroke=0, fill=1)
        _outline(c, W, H)


def t_elegan(c, k, W, H, hor):
    hi = _mix(k.accent, WHITE, .6)  # aksen terang agar terbaca di latar gelap
    sub = colors.HexColor("#98a2b3")
    c.setFillColor(DARK_BG)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    # ornamen lingkaran
    c.setStrokeColor(k.accent); c.setLineWidth(.5)
    for r, a in ((30, .45), (38, .3), (46, .18)):
        c.setStrokeAlpha(a)
        c.circle(W if hor else W, H if hor else H, r, stroke=1, fill=0)
    c.setStrokeAlpha(1)
    c.setFillColor(k.accent); c.setFillAlpha(.22)
    c.circle(0, 0, 24 if hor else 20, stroke=0, fill=1)
    c.setFillAlpha(1)
    if hor:
        _logo(c, k, 8.2, H - 7.6, 3.6, bg=WHITE)
        _text_fit(c, k.sekolah.upper(), 13.8, H - 7.2, W - 18, F["b"], 6.5, WHITE, min_size=4.3)
        _text(c, "STUDENT ID  ·  KARTU PELAJAR", 13.8, H - 10.4, F["m"], 4.2, hi, spacing=.4)
        _photo(c, k, 5, 6, 20, 25.5, r=1.6, ring=hi, ring_w=.45)
        tx = 29
        _name(c, k.nama, tx, 32.2, W - tx - 4.5, 9.4, WHITE, min_size=6.8)
        _text_fit(c, f"Kelas {k.kelas}", tx, 27.4, 26, F["sb"], 6.6, hi)
        c.setFillColor(hi); c.rect(tx, 25, 8, .45, stroke=0, fill=1)
        _text(c, "NIS", tx, 19.6, F["m"], 4.5, sub, spacing=.3)
        _text_fit(c, k.nis, tx, 16.4, 12, F["sb"], 6.2, WHITE)
        _text(c, "NISN", tx + 14, 19.6, F["m"], 4.5, sub, spacing=.3)
        _text_fit(c, k.nisn, tx + 14, 16.4, 13, F["sb"], 6.2, WHITE)
        _qr(c, k, W - 5 - 19.5, 6.5, 19.5, pad=1.6, radius=2)
    else:
        _logo(c, k, W / 2, H - 7.4, 3.6, bg=WHITE)
        _text_fit(c, k.sekolah.upper(), W / 2, H - 14.2, W - 7, F["b"], 5.9, WHITE, "c", 4)
        _text(c, "STUDENT ID  ·  KARTU PELAJAR", W / 2, H - 17.4, F["m"], 3.8, hi, "c", spacing=.35)
        c.setFillColor(hi); c.rect(W / 2 - 5, H - 19.6, 10, .45, stroke=0, fill=1)
        ex = _name_extra(k.nama, W - 7, 8.8, 6.3)
        ph = 27 - ex
        _photo(c, k, W / 2 - ph * 21 / 54, H - 23.5 - ph, ph * 21 / 27, ph, r=1.6, ring=hi, ring_w=.45)
        _name(c, k.nama, W / 2, 30.2, W - 7, 8.8, WHITE, "c", min_size=6.3)
        _text_fit(c, f"Kelas {k.kelas}", W / 2, 26.2, W - 8, F["sb"], 6, hi, "c", 4.5)
        _text_fit(c, f"NIS {k.nis}  ·  NISN {k.nisn}", W / 2, 22.7, W - 8, F["m"], 4.9, sub, "c", 3.8)
        _qr(c, k, W / 2 - 7.8, 4.6, 15.6, pad=1.5, radius=2)


def t_gradien(c, k, W, H, hor):
    c.saveState()
    c.linearGradient(0, 0, W, H, (k.dark, k.accent, _mix(k.accent, WHITE, .2)), (0, .55, 1),
                     extend=True)
    c.restoreState()
    c.setFillColor(WHITE)
    for cx, cy, r, a in ((W * .95, H * 1.02, 22, .09), (W * .08, -H * .08, 18, .07),
                         (W * .78, H * .1, 9, .06)):
        c.setFillAlpha(a); c.circle(cx, cy, r, stroke=0, fill=1)
    c.setFillAlpha(1)
    soft = colors.Color(1, 1, 1, alpha=.78)
    if hor:
        _logo(c, k, 7.8, H - 7.4, 3.5, bg=WHITE)
        _text_fit(c, k.sekolah.upper(), 13.4, H - 7, W - 18, F["b"], 6.6, WHITE, min_size=4.3)
        _text(c, "KARTU PELAJAR", 13.4, H - 10.2, F["sb"], 4.3, soft, spacing=.55)
        _photo(c, k, 5.5, 9, 21, 21, circle=True, ring=WHITE, ring_w=.9)
        tx = 31
        _name(c, k.nama, tx, 31.6, W - tx - 4.5, 9.6, WHITE, min_size=6.8)
        # "kaca" semi transparan untuk kelas
        kel = f"Kelas {k.kelas}"
        pw = _sw(kel, F["sb"], 6) + 4.4
        c.setFillColor(WHITE); c.setFillAlpha(.18)
        c.roundRect(tx, 24.7, pw, 4.3, 2.15, stroke=0, fill=1); c.setFillAlpha(1)
        _text(c, kel, tx + 2.2, 26.1, F["sb"], 6, WHITE)
        _text(c, "NIS", tx, 18.8, F["m"], 4.4, soft, spacing=.3)
        _text_fit(c, k.nis, tx, 15.6, 11, F["sb"], 6.2, WHITE)
        _text(c, "NISN", tx + 13, 18.8, F["m"], 4.4, soft, spacing=.3)
        _text_fit(c, k.nisn, tx + 13, 15.6, 12, F["sb"], 6.2, WHITE)
        _qr(c, k, W - 5 - 18.5, 6, 18.5, pad=1.7, radius=2.2)
    else:
        _logo(c, k, W / 2, H - 7.2, 3.5, bg=WHITE)
        _text_fit(c, k.sekolah.upper(), W / 2, H - 14, W - 7, F["b"], 5.9, WHITE, "c", 4)
        _text(c, "KARTU PELAJAR", W / 2, H - 17.3, F["sb"], 4, soft, "c", spacing=.55)
        ex = _name_extra(k.nama, W - 7, 9, 6.4)
        d = 22 - ex
        _photo(c, k, W / 2 - d / 2, H - 22.5 - d, d, d, circle=True, ring=WHITE, ring_w=.9)
        _name(c, k.nama, W / 2, 34.3, W - 7, 9, WHITE, "c", min_size=6.4)
        kel = f"Kelas {k.kelas}"
        pw = _sw(kel, F["sb"], 5.6) + 4
        c.setFillColor(WHITE); c.setFillAlpha(.18)
        c.roundRect(W / 2 - pw / 2, 28.4, pw, 4, 2, stroke=0, fill=1); c.setFillAlpha(1)
        _text(c, kel, W / 2, 29.7, F["sb"], 5.6, WHITE, "c")
        _text_fit(c, f"NIS {k.nis}  ·  NISN {k.nisn}", W / 2, 24.9, W - 8, F["m"], 4.9, soft, "c", 3.8)
        _qr(c, k, W / 2 - 8, 4.6, 16, pad=1.6, radius=2)


DRAW = {"modern": t_modern, "klasik": t_klasik, "minimal": t_minimal, "elegan": t_elegan,
        "gradien": t_gradien}


def draw_card(c, x, y, k, template, hor):
    W, H = (CARD_LONG, CARD_SHORT) if hor else (CARD_SHORT, CARD_LONG)
    c.saveState()
    c.translate(x, y)
    c.scale(mm, mm)
    c.saveState()
    _clip_card(c, W, H)
    DRAW.get(template, t_modern)(c, k, W, H, hor)
    c.restoreState()
    c.restoreState()


def normalize(template=None, orientasi=None, warna=None):
    return (template if template in TEMPLATES else DEFAULT["template"],
            orientasi if orientasi in ORIENTASI else DEFAULT["orientasi"],
            warna if warna in WARNA else DEFAULT["warna"])


def kartu_pdf(siswa_rows, sekolah, template="modern", orientasi="h", warna="biru", alamat="",
              logo=None, db=None, single=False):
    """PDF kartu. `single=True` → satu kartu per halaman seukuran kartu (untuk pratinjau)."""
    template, orientasi, warna = normalize(template, orientasi, warna)
    hor = orientasi == "h"
    accent = WARNA[warna][1]
    W, H = ((CARD_LONG, CARD_SHORT) if hor else (CARD_SHORT, CARD_LONG))
    W, H = W * mm, H * mm
    buf = io.BytesIO()
    if single:
        pad = 4 * mm
        c = canvas.Canvas(buf, pagesize=(W + 2 * pad, H + 2 * pad))
        c.setTitle("Pratinjau Kartu Pelajar")
        for i, s in enumerate(siswa_rows):
            if i:
                c.showPage()
            c.setFillColor(colors.HexColor("#f2f4f7"))
            c.rect(0, 0, W + 2 * pad, H + 2 * pad, stroke=0, fill=1)
            draw_card(c, pad, pad, Ctx(s, sekolah, alamat, logo, accent, db), template, hor)
        c.save()
        buf.seek(0)
        return buf

    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Kartu Pelajar")
    pw, ph = A4
    cols, rows = (2, 5) if hor else (3, 3)
    gap = 5 * mm if hor else 4 * mm
    mx = (pw - cols * W - (cols - 1) * gap) / 2
    my = (ph - rows * H - (rows - 1) * gap) / 2
    per = cols * rows
    for i, s in enumerate(siswa_rows):
        if i and i % per == 0:
            c.showPage()
        idx = i % per
        col, row = idx % cols, idx // cols
        x = mx + col * (W + gap)
        y = ph - my - (row + 1) * H - row * gap
        draw_card(c, x, y, Ctx(s, sekolah, alamat, logo, accent, db), template, hor)
    if not siswa_rows:
        c.setFont(F["r"], 11)
        c.drawString(40, ph - 60, "Tidak ada siswa.")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pdf_to_png(pdf_buf, scale=3):
    """Render halaman pertama PDF menjadi PNG (butuh pypdfium2). None bila tidak tersedia."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    doc = pdfium.PdfDocument(pdf_buf.read())
    try:
        img = doc[0].render(scale=scale).to_pil()
    finally:
        doc.close()
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def png_available():
    try:
        import pypdfium2  # noqa: F401
        return True
    except ImportError:
        return False
