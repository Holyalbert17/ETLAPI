import traceback
from typing import Any

from sqlalchemy import String, asc, cast, desc, func
from sqlalchemy.orm import Session

from app.domain.models import (
    AuditLog,
    DataSource,
    DynamicRecord,
    ErrorLog,
    ExtractionJob,
    RawRecord,
    SchemaSnapshot,
)
from app.ports.base_repository import BaseRepository
from app.security import redact
from app.services.identifiers import UnsafeIdentifier, validate_ident
from app.services.schema_diff import allowed_columns


class SqlRepository(BaseRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_source(self, source_id: int) -> DataSource | None:
        return self.db.get(DataSource, source_id)

    def get_source_by_name(self, name: str) -> DataSource | None:
        return self.db.query(DataSource).filter_by(name=name).first()

    def save_job(self, job: ExtractionJob) -> None:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

    def log_error(
        self,
        job_id: int | None,
        stage: str,
        exc: Exception,
        payload: dict | None = None,
        source_name: str | None = None,
    ) -> None:
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.db.add(
            ErrorLog(
                job_id=job_id,
                source_name=source_name,
                stage=stage,
                message=redact(str(exc))[:4000],
                stack_trace=redact(stack)[:8000],
                payload=payload,
            )
        )
        self.db.commit()

    def delete_source(self, source: DataSource) -> None:
        source_id = source.id
        job_ids = [
            row[0]
            for row in self.db.query(ExtractionJob.id).filter_by(source_id=source_id).all()
        ]
        if job_ids:
            self.db.query(ErrorLog).filter(ErrorLog.job_id.in_(job_ids)).delete(synchronize_session=False)
        self.db.query(ExtractionJob).filter_by(source_id=source_id).delete(synchronize_session=False)
        self.db.query(DynamicRecord).filter_by(source_id=source_id).delete(synchronize_session=False)
        self.db.query(RawRecord).filter_by(source_id=source_id).delete(synchronize_session=False)
        self.db.query(SchemaSnapshot).filter_by(source_id=source_id).delete(synchronize_session=False)
        self.db.delete(source)
        self.db.commit()

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
    ) -> dict:
        validate_ident(table, what="tabla")
        mapping = (source.canonical_mapping or {}).get(table)
        if source.discovered_schema:
            known = {item.get("name") for item in source.discovered_schema.get("tables", [])}
            if table not in known:
                raise LookupError(f"Tabla no conocida en el origen: {table}")
        whitelist = allowed_columns(source.discovered_schema, table, mapping)

        selected = columns or None
        if selected is not None:
            for column in selected:
                self._ensure_column(column, whitelist)

        query = self.db.query(DynamicRecord).filter_by(source_id=source.id, table_name=table)
        for item in filters:
            field = self._ensure_column(str(item.get("field")), whitelist)
            op = item.get("op") or "eq"
            value = item.get("value")
            column = self._json_text(field)
            query = self._apply_filter(query, column, op, value)

        total = query.count()
        query = self._apply_order(query, order_by, whitelist)
        rows = query.offset(offset).limit(limit).all()
        data = [row.data for row in rows]
        if selected is not None:
            data = [{key: item.get(key) for key in selected} for item in data]
        return {"total": total, "limit": limit, "offset": offset, "data": data}

    def list_tables(self, source_id: int) -> list[str]:
        rows = (
            self.db.query(DynamicRecord.table_name)
            .filter_by(source_id=source_id)
            .distinct()
            .all()
        )
        return sorted({row[0] for row in rows})

    def _ensure_column(self, field: str, whitelist: set[str] | None) -> str:
        validate_ident(field, what="columna")
        if whitelist is not None and field not in whitelist:
            raise UnsafeIdentifier(f"Columna fuera de la lista permitida: {field}")
        return field

    def _json_text(self, field: str):
        dialect = self.db.get_bind().dialect.name
        if dialect == "postgresql":
            return DynamicRecord.data[field].astext
        return cast(func.json_extract(DynamicRecord.data, f"$.{field}"), String)

    def _apply_order(self, query, order_by: str | None, whitelist: set[str] | None):
        if not order_by:
            return query.order_by(asc(DynamicRecord.id))
        direction = desc if order_by.startswith("-") else asc
        field = order_by[1:] if order_by.startswith("-") else order_by
        if field == "id":
            return query.order_by(direction(DynamicRecord.id))
        if field in {"created_at", "updated_at"}:
            column = getattr(DynamicRecord, field)
            return query.order_by(direction(column))
        safe = self._ensure_column(field, whitelist)
        return query.order_by(direction(self._json_text(safe)), asc(DynamicRecord.id))

    @staticmethod
    def _apply_filter(query, column, op: str, value: Any):
        if op == "eq":
            return query.filter(column == ("" if value is None else str(value)))
        if op == "ne":
            return query.filter(column != ("" if value is None else str(value)))
        if op == "gt":
            return query.filter(column > str(value))
        if op == "lt":
            return query.filter(column < str(value))
        if op == "like":
            return query.filter(column.like(f"%{value}%"))
        if op == "in":
            if not isinstance(value, list) or not value:
                raise UnsafeIdentifier("El operador 'in' requiere una lista de valores")
            return query.filter(column.in_([str(item) for item in value]))
        raise UnsafeIdentifier(f"Operador no permitido: {op}")


def write_audit(
    db: Session,
    *,
    username: str | None,
    action: str,
    resource: str,
    detail: dict | None = None,
) -> None:
    db.add(AuditLog(username=username, action=action, resource=resource, detail=detail))
    db.commit()
