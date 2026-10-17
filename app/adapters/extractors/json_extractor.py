import json
from collections.abc import Iterator

from app.domain.schemas import SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor
from app.services.infer import dig, infer_columns
from app.services.normalizer import to_jsonable


class JSONExtractor(BaseExtractor):
    """config: {"path": "datos.json", "records_path": "items", "table": "default"}."""

    def connect(self) -> None:
        path = self.config.get("path")
        if not path:
            raise ValueError("JSON requiere 'path'")
        with open(path, encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        records = dig(payload, self.config.get("records_path"))
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list):
            raise ValueError("El JSON no contiene una lista de registros")
        self.records = [to_jsonable(item) for item in records if isinstance(item, dict)]

    def close(self) -> None:
        return None

    def _table(self) -> str:
        return self.config.get("table") or "default"

    def discover_schema(self) -> SourceSchema:
        if not hasattr(self, "records"):
            self.connect()
        return SourceSchema(
            tables=[TableInfo(name=self._table(), columns=infer_columns(self.records[:50]))]
        )

    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]:
        del table, batch_size
        if not hasattr(self, "records"):
            self.connect()
        skip = int((checkpoint or {}).get("skip") or 0)
        for record in self.records[skip:]:
            self.bytes_read += len(json.dumps(record, default=str))
            yield record
