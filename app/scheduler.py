"""Job background (APScheduler):
- proses antrian WA (tiap 20 detik)
- tutup harian: tandai Belum Pulang & Alpha setelah jam tutup (tiap menit)
- cek kuota Fonnte (tiap jam)
- backup harian database lokal
"""
import logging
import os
import sqlite3
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from . import config, utils
from .db import standalone

log = logging.getLogger(__name__)
_scheduler = None


def _job(app, fn):
    def run():
        with app.app_context():
            try:
                with standalone() as db:
                    fn(db)
            except Exception:
                log.exception("Job %s gagal", fn.__name__)
    return run


def job_notif(db):
    from .services.notify import process_queue
    process_queue(db)


def job_tutup_harian(db):
    from .services.attendance import close_day
    close_day(db)


def job_kuota(db):
    from .services.notify import refresh_quota
    refresh_quota(db)


def job_lisensi(db):
    """Catat tanggal (anti jam mundur) & cek status lisensi ke server bila online."""
    from .license import touch_last_seen
    from .services.lisensi import check_online
    touch_last_seen(db)
    check_online(db)


def job_backup(db):
    """Salin database ke data/backup/presensi-YYYY-MM-DD.db (simpan 14 terakhir)."""
    config.ensure_dirs()
    dest = os.path.join(config.BACKUP_DIR, f"presensi-{utils.today_str()}.db")
    target = sqlite3.connect(dest)
    db.backup(target)
    target.close()
    files = sorted(f for f in os.listdir(config.BACKUP_DIR) if f.startswith("presensi-"))
    for old in files[:-14]:
        os.remove(os.path.join(config.BACKUP_DIR, old))


def start(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    from .services.attendance import catch_up
    with app.app_context(), standalone() as db:
        try:
            catch_up(db)
        except Exception:
            log.exception("catch_up gagal")
    s = BackgroundScheduler(daemon=True)
    s.add_job(_job(app, job_notif), "interval", seconds=20, id="notif", max_instances=1,
              coalesce=True)
    s.add_job(_job(app, job_tutup_harian), "interval", minutes=1, id="tutup", max_instances=1,
              coalesce=True)
    s.add_job(_job(app, job_kuota), "interval", hours=1, id="kuota", max_instances=1)
    s.add_job(_job(app, job_backup), "cron", hour=12, minute=30, id="backup")
    s.add_job(_job(app, job_lisensi), "interval", hours=6, id="lisensi", max_instances=1,
              next_run_time=utils.now() + timedelta(seconds=30))
    s.start()
    _scheduler = s
    return s
