import logging

from app.config import settings
from app.database import SessionLocal
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def run_extraction_task(source_id: int, job_id: int, mode: str = "full") -> None:
    setup_logging(settings.LOG_LEVEL)
    from app.services.extractor_service import ExtractorService

    db = SessionLocal()
    try:
        ExtractorService(db).run(source_id, job_id, mode)
    except Exception:
        logger.exception("El worker no pudo ejecutar el job %s", job_id)
    finally:
        db.close()
