import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.domain.models import DataSource
from app.queueing import dispatch_extraction
from app.services.jobs import create_extraction_job

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def parse_trigger(expression: str):
    if expression.startswith("@every"):
        parts = expression.split()
        if len(parts) != 2 or not parts[1].endswith("s") or not parts[1][:-1].isdigit():
            raise ValueError("Intervalo inválido. Usa el formato @every 300s")
        seconds = int(parts[1][:-1])
        if seconds < 1:
            raise ValueError("El intervalo debe ser de al menos 1s")
        return IntervalTrigger(seconds=seconds)
    return CronTrigger.from_crontab(expression)


def validate_schedule(expression: str | None) -> None:
    if expression:
        parse_trigger(expression)


def _scheduled(source_id: int) -> None:
    db = SessionLocal()
    try:
        source = db.get(DataSource, source_id)
        if source is None or not source.active:
            return
        mode = "delta" if source.incremental_column else "full"
        job = create_extraction_job(db, source, mode=mode)
        job_id = job.id
        source_name = source.name
    finally:
        db.close()
    logger.info("Scheduler dispara %s", source_name, extra={"source_id": source_id, "job_id": job_id})
    dispatch_extraction(source_id, job_id, mode)


def sync_schedules(db: Session) -> None:
    if not settings.ENABLE_SCHEDULER:
        return
    scheduler.remove_all_jobs()
    sources = db.query(DataSource).filter_by(active=True).all()
    for source in sources:
        if not source.schedule:
            continue
        try:
            trigger = parse_trigger(source.schedule)
        except Exception as exc:
            logger.warning("Schedule inválido para %s: %s", source.name, exc)
            continue
        scheduler.add_job(
            _scheduled,
            trigger,
            args=[source.id],
            id=f"src-{source.id}",
            replace_existing=True,
        )
        logger.info("Programado %s con %s", source.name, source.schedule)


def start_scheduler() -> None:
    if not settings.ENABLE_SCHEDULER or scheduler.running:
        return
    db = SessionLocal()
    try:
        sync_schedules(db)
    finally:
        db.close()
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
