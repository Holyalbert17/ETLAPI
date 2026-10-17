from abc import ABC, abstractmethod


class BaseLoader(ABC):
    @abstractmethod
    def upsert(
        self,
        source_id: int,
        table: str,
        records: list[dict],
        key: list[str],
    ) -> tuple[int, int, int]:
        """Persiste un lote. Devuelve (insertados, actualizados, duplicados)."""
