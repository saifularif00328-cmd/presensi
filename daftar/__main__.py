"""Jalankan halaman depan + pendaftaran demo:  python -m daftar  (127.0.0.1:7000)."""
import os

from . import create_app

if __name__ == "__main__":
    host = os.environ.get("DAFTAR_HOST", "127.0.0.1")
    port = int(os.environ.get("DAFTAR_PORT", "7000"))
    try:
        from waitress import serve  # server produksi (dipasang install_vps.sh)
        serve(create_app(), host=host, port=port, threads=4)
    except ImportError:
        create_app().run(host=host, port=port, debug=False, use_reloader=False)
