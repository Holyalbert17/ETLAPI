from collections.abc import Iterator

from pymongo import MongoClient

from app.domain.schemas import SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor
from app.services.infer import infer_columns
from app.services.normalizer import to_jsonable


class MongoDBExtractor(BaseExtractor):
    """config: {"uri": "mongodb://localhost:27017", "database": "mydb", "tables": ["opcional"]}."""

    def connect(self) -> None:
        if "uri" not in self.config or "database" not in self.config:
            raise ValueError("MongoDB requiere 'uri' y 'database'")
        self.client = MongoClient(self.config["uri"], serverSelectionTimeoutMS=5000)
        self.db = self.client[self.config["database"]]

    def close(self) -> None:
        client = getattr(self, "client", None)
        if client is not None:
            client.close()

    def discover_schema(self) -> SourceSchema:
        names = self.db.list_collection_names()
        allowed = self.config.get("tables")
        if allowed:
            missing = [name for name in allowed if name not in names]
            if missing:
                raise ValueError(f"Colecciones no encontradas: {missing}")
            names = [name for name in names if name in set(allowed)]
        tables: list[TableInfo] = []
        for name in names:
            sample = [to_jsonable(doc) for doc in self.db[name].find().limit(20)]
            for doc in sample:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
            tables.append(TableInfo(name=name, columns=infer_columns(sample)))
        return SourceSchema(tables=tables)

    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]:
        skip = int((checkpoint or {}).get("skip") or 0)
        cursor = self.db[table].find().skip(skip).batch_size(batch_size)
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            yield to_jsonable(doc)
