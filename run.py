"""Jalankan server Presensi Siswa Digital.

    python run.py

Lalu buka http://localhost:5000 di browser (atau http://<IP-komputer>:5000 dari HP
di jaringan WiFi yang sama). Login awal: admin / admin123 (segera ganti).
"""
import logging
import sys
import threading
import webbrowser

from app import create_app, utils
from app.config import HOST, PORT


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    print("=" * 60)
    print(" Presensi Siswa Digital")
    print(f"  Komputer ini : http://localhost:{PORT}")
    print(f"  HP / perangkat lain (WiFi sama): http://{utils.local_ip()}:{PORT}")
    print("  Tekan Ctrl+C untuk berhenti")
    print("=" * 60)
    if getattr(sys, "frozen", False) or "--open" in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    try:
        from waitress import serve  # server produksi bila tersedia
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
