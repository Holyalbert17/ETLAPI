import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def notify_critical(message: str, extra: dict | None = None) -> None:
    payload = {"message": message, **(extra or {})}
    logger.error(message, extra={key: value for key, value in payload.items() if key != "message"})
    if not settings.ERROR_WEBHOOK_URL:
        return
    try:
        httpx.post(settings.ERROR_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        logger.warning("No se pudo notificar el webhook de error")
