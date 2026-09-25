"""Helper bersama untuk blueprint."""
import re

from flask import request, send_file

from .. import utils
from ..db import query
from ..services.export import pdf_table, xlsx


def kelas_options():
    return query("SELECT id, nama, jenjang FROM kelas ORDER BY jenjang, nama")


def siswa_options(kelas_id=None):
    if kelas_id:
        return query("SELECT s.id, s.nama, s.nis, k.nama AS kelas_nama FROM siswa s "
                     "LEFT JOIN kelas k ON k.id = s.kelas_id WHERE s.aktif = 1 AND s.kelas_id = ? "
                     "ORDER BY s.nama", (kelas_id,))
    return query("SELECT s.id, s.nama, s.nis, k.nama AS kelas_nama FROM siswa s "
                 "LEFT JOIN kelas k ON k.id = s.kelas_id WHERE s.aktif = 1 "
                 "ORDER BY k.nama, s.nama")


def arg_int(name, default=None):
    v = request.args.get(name, "")
    return int(v) if v.isdigit() else default


def form_int(name, default=None):
    v = request.form.get(name, "")
    return int(v) if v.strip().isdigit() else default


def arg_date(name, default=None):
    return utils.parse_date(request.args.get(name), default)


def valid_time(v):
    return bool(v) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?", v) is not None


def send_export(fmt, filename, title, headers, rows, subtitle=None):
    """Kirim rekap sebagai .xlsx atau .pdf sesuai parameter `format`."""
    if fmt == "pdf":
        buf = pdf_table(title, headers, rows, subtitle)
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                         download_name=f"{filename}.pdf")
    buf = xlsx(title, headers, rows, subtitle)
    return send_file(buf, as_attachment=True, download_name=f"{filename}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def semester_aktif():
    return query("SELECT * FROM tahun_ajaran WHERE aktif = 1 ORDER BY id DESC LIMIT 1", one=True)
