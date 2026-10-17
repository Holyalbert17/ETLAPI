import csv
from collections.abc import Iterator

from app.domain.schemas import ColumnInfo, SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor


class CSVExtractor(BaseExtractor):
    """config: {"path": "datos.csv", "delimiter": ",", "table": "default"}."""

    def connect(self) -> None:
        path = self.config.get("path")
        if not path:
            raise ValueError("CSV requiere 'path'")
        delimiter = self.config.get("delimiter", ",")
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            try:
                self.headers = next(reader)
            except StopIteration as exc:
                raise ValueError("El CSV está vacío") from exc
        self.headers = [header.strip() for header in self.headers]

    def close(self) -> None:
        return None

    def _table(self) -> str:
        return self.config.get("table") or "default"

    def discover_schema(self) -> SourceSchema:
        headers = getattr(self, "headers", None)
        if headers is None:
            self.connect()
            headers = self.headers
        columns = [ColumnInfo(name=header, type="string", nullable=True) for header in headers]
        return SourceSchema(tables=[TableInfo(name=self._table(), columns=columns)])

    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]:
        del table, batch_size
        skip = int((checkpoint or {}).get("skip") or 0)
        with open(self.config["path"], newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter=self.config.get("delimiter", ","))
            for index, row in enumerate(reader):
                if index < skip:
                    continue
                self.bytes_read += len(",".join("" if value is None else str(value) for value in row.values()))
                yield {key.strip(): value for key, value in row.items() if key is not None}
