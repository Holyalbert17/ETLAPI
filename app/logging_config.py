import json
import logging
import sys
from datetime import datetime, timezone

from app.context import correlation_id_ctx


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = correlation_id_ctx.get()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key in ("job_id", "source_id", "stage", "correlation_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "apscheduler", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
