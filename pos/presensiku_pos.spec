# PyInstaller: pyinstaller pos/presensiku_pos.spec  ->  dist/PresensikuPos/PresensikuPos.exe
# (dijalankan dari folder repo; layar Gerbang memakai berkas yang sama dengan server)
import os

akar = os.path.abspath(".")
statis = [
    (os.path.join(akar, "app", "static", "js", "layar_gerbang.js"), "statis"),
    (os.path.join(akar, "app", "static", "css", "layar_gerbang.css"), "statis"),
    (os.path.join(akar, "app", "templates", "presensi", "_layar_isi.html"), "statis"),
]

a = Analysis([os.path.join(akar, "pos", "jalankan.py")], pathex=[os.path.join(akar, "pos")],
             datas=statis, hiddenimports=["serial.tools.list_ports"], excludes=["tkinter"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PresensikuPos", console=False,
          icon=None, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="PresensikuPos")
