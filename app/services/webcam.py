"""Scanner webcam PC di sisi server (OpenCV + pyzbar) — opsional.

Dipakai bila komputer server memiliki webcam. Hasil scan diproses sama persis
seperti scan dari browser, dan tampil di Monitor Live. Bila paket opencv-python
/ pyzbar tidak terpasang, fitur ini otomatis nonaktif.
"""
import logging
import threading
import time

log = logging.getLogger(__name__)

_state = {"thread": None, "stop": None, "mode": "auto", "last": None, "error": None}


def import_error():
    """None bila OpenCV & pyzbar bisa dimuat, selain itu pesan error-nya."""
    try:
        import cv2  # noqa: F401
    except Exception as e:
        return f"opencv-python: {type(e).__name__}: {e}"
    try:
        from pyzbar import pyzbar  # noqa: F401
    except Exception as e:  # di Windows sering karena DLL zbar / VC++ 2013 tidak ada
        return f"pyzbar: {type(e).__name__}: {e}"
    return None


def available():
    return import_error() is None


def running():
    t = _state["thread"]
    return t is not None and t.is_alive()


def status():
    err = import_error()
    return {"available": err is None, "import_error": err, "running": running(),
            "mode": _state["mode"], "last": _state["last"], "error": _state["error"]}


def start(app, camera_index=0, mode="auto"):
    if running():
        _state["mode"] = mode
        return True
    if not available():
        _state["error"] = "opencv-python / pyzbar belum terpasang"
        return False
    stop = threading.Event()
    _state.update(stop=stop, mode=mode, error=None)
    t = threading.Thread(target=_loop, args=(app, camera_index, stop), daemon=True,
                         name="webcam-scanner")
    _state["thread"] = t
    t.start()
    return True


def stop():
    if _state["stop"] is not None:
        _state["stop"].set()


def _loop(app, camera_index, stop_event):
    import cv2
    from pyzbar import pyzbar

    from ..db import standalone
    from .attendance import process_scan

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        _state["error"] = f"Kamera {camera_index} tidak dapat dibuka"
        return
    last_code, last_time = None, 0.0
    try:
        while not stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.2)
                continue
            for code in pyzbar.decode(frame):
                text = code.data.decode("utf-8", "ignore")
                # Cegah kartu yang sama terbaca berulang dalam 3 detik
                if text == last_code and time.time() - last_time < 3:
                    continue
                last_code, last_time = text, time.time()
                with app.app_context(), standalone() as db:
                    res = process_scan(text, _state["mode"], "webcam", db=db)
                _state["last"] = res
            time.sleep(0.05)
    except Exception as e:  # pragma: no cover - bergantung perangkat keras
        log.exception("Webcam scanner berhenti")
        _state["error"] = str(e)
    finally:
        cap.release()
