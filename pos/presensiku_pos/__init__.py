"""Presensiku Pos — aplikasi PC pos sekolah untuk banyak scanner sekaligus.

- Membaca scanner USB mode keyboard per alat (Windows Raw Input), scanner mode COM, dan dongle
  nirkabel, tanpa saling tercampur.
- Mengirim scan ke server sekolah (HMAC), menyimpan antrean saat internet putus.
- Menyajikan Layar Gerbang di http://127.0.0.1:8765 (tetap jalan offline memakai salinan data
  siswa).
"""
VERSI = "1.0.0"
