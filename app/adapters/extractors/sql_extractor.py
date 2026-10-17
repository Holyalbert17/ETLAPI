import json
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text

from app.domain.schemas import ColumnInfo, RelationInfo, SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor
from app.services.identifiers import qualified_name, quote_ident


class SQLAlchemyExtractor(BaseExtractor):
    quote_style = "ansi"
    default_schema: str | None = None

    def connect(self) -> None:
        if "dsn" not in self.config:
            raise ValueError("La configuración SQL requiere 'dsn'")
        self.engine = create_engine(self.config["dsn"], pool_pre_ping=True)

    def close(self) -> None:
        engine = getattr(self, "engine", None)
        if engine is not None:
            engine.dispose()

    def _schema_name(self) -> str | None:
        if "schema" in self.config:
            schema = self.config.get("schema")
            return schema or None
        return self.default_schema

    def _selected_tables(self, names: list[str]) -> list[str]:
        allowed = self.config.get("tables")
        if not allowed:
            return list(names)
        missing = [name for name in allowed if name not in names]
        if missing:
            raise ValueError(f"Tablas no encontradas: {missing}")
        allowed_set = set(allowed)
        return [name for name in names if name in allowed_set]

    def discover_schema(self) -> SourceSchema:
        inspector = inspect(self.engine)
        schema_name = self._schema_name()
        tables: list[TableInfo] = []
        for table_name in self._selected_tables(inspector.get_table_names(schema=schema_name)):
            pk = inspector.get_pk_constraint(table_name, schema=schema_name).get("constrained_columns") or []
            columns = [
                ColumnInfo(
                    name=column["name"],
                    type=str(column["type"]),
                    nullable=bool(column.get("nullable", True)),
                    primary_key=column["name"] in pk,
                )
                for column in inspector.get_columns(table_name, schema=schema_name)
            ]
            relations: list[RelationInfo] = []
            for foreign_key in inspector.get_foreign_keys(table_name, schema=schema_name):
                constrained = foreign_key.get("constrained_columns") or []
                referred = foreign_key.get("referred_columns") or []
                referred_table = foreign_key.get("referred_table") or ""
                for column_name, referred_column in zip(constrained, referred, strict=False):
                    relations.append(
                        RelationInfo(
                            column=column_name,
                            referred_table=referred_table,
                            referred_column=referred_column,
                        )
                    )
            tables.append(TableInfo(name=table_name, columns=columns, relations=relations))
        return SourceSchema(tables=tables)

    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]:
        checkpoint = checkpoint or {}
        qualified = qualified_name(self._schema_name(), table, self.quote_style)
        incremental = self.config.get("incremental_column")
        watermark = checkpoint.get("watermark")
        offset = int(checkpoint.get("skip") or 0)
        where = ""
        order = ""
        if incremental and watermark not in (None, ""):
            column_sql = quote_ident(str(incremental), self.quote_style)
            where = f" WHERE {column_sql} > :wm"
            order = f" ORDER BY {column_sql}"
        statement = text(f"SELECT * FROM {qualified}{where}{order} LIMIT :limit OFFSET :offset")
        with self.engine.connect() as connection:
            while True:
                params: dict = {"limit": batch_size, "offset": offset}
                if where:
                    params["wm"] = watermark
                result = connection.execute(statement, params)
                rows = [dict(row) for row in result.mappings()]
                if not rows:
                    break
                self.bytes_read += len(json.dumps(rows, default=str))
                yield from rows
                offset += len(rows)
                if len(rows) < batch_size:
                    break
