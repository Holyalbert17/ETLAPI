from abc import ABC, abstractmethod
from typing import Any

from app.domain.models import DataSource, ExtractionJob


class BaseRepository(ABC):
    @abstractmethod
    def get_source(self, source_id: int) -> DataSource | None: ...

    @abstractmethod
    def save_job(self, job: ExtractionJob) -> None: ...

    @abstractmethod
    def log_error(
        self,
        job_id: int | None,
        stage: str,
        exc: Exception,
        payload: dict | None = None,
        source_name: str | None = None,
    ) -> None: ...

    @abstractmethod
    def query_dynamic(
        self,
        source: DataSource,
        table: str,
        *,
        columns: list[str] | None,
        filters: list[dict[str, Any]],
        limit: int,
        offset: int,
        order_by: str | None,
    ) -> dict: ...
