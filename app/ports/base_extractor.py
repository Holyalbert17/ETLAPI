from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.domain.schemas import SourceSchema


class BaseExtractor(ABC):
    """Puerto de lectura. Un adaptador nuevo hereda esta clase y se registra en la factory."""

    def __init__(self, config: dict):
        self.config = config
        self.bytes_read = 0
        self.last_http_status: int | None = None

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def discover_schema(self) -> SourceSchema: ...

    @abstractmethod
    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]: ...

    @abstractmethod
    def close(self) -> None: ...
