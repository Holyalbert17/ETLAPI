import logging

from app.config import settings

logger = logging.getLogger(__name__)


def dispatch_extraction(source_id: int, job_id: int, mode: str = "full", background=None) -> None:
    """Encola el job en Redis/RQ si hay broker; si no, lo ejecuta al terminar la request."""
    if settings.REDIS_URL:
        from redis import Redis
        from rq import Queue

        queue = Queue("extraction", connection=Redis.from_url(settings.REDIS_URL))
        queue.enqueue("app.worker.run_extraction_task", source_id, job_id, mode)
        logger.info("Job %s encolado", job_id, extra={"job_id": job_id, "source_id": source_id})
        return
    from app.worker import run_extraction_task

    if background is not None:
        background.add_task(run_extraction_task, source_id, job_id, mode)
        return
    run_extraction_task(source_id, job_id, mode)
