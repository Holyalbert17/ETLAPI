from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.domain.models import DynamicRecord, RawRecord
from app.ports.base_loader import BaseLoader
from app.services.dedup import content_hash, natural_key
from app.services.normalizer import to_jsonable


class PostgresLoader(BaseLoader):
    """Carga en dynamic_records (staging) aplicando la política de duplicados."""

    def __init__(self, db: Session, dedup_policy: str = "upsert"):
        self.db = db
        self.policy = dedup_policy

    def store_raw(self, source_id: int, job_id: int | None, table: str, records: list[dict]) -> None:
        if not records:
            return
        self.db.add_all(
            [
                RawRecord(
                    source_id=source_id,
                    job_id=job_id,
                    table_name=table,
                    data=to_jsonable(record),
                )
                for record in records
            ]
        )

    def upsert(
        self,
        source_id: int,
        table: str,
        records: list[dict],
        key: list[str],
    ) -> tuple[int, int, int]:
        prepared: list[tuple[dict, str | None, str]] = []
        natural_keys: list[str] = []
        hashes: list[str] = []
        for record in records:
            safe = to_jsonable(record)
            digest = content_hash(safe)
            key_value = natural_key(safe, key)
            prepared.append((safe, key_value, digest))
            if key_value is not None:
                natural_keys.append(key_value)
            else:
                hashes.append(digest)

        existing: dict[str, DynamicRecord] = {}
        if natural_keys:
            rows = (
                self.db.query(DynamicRecord)
                .filter(
                    DynamicRecord.source_id == source_id,
                    DynamicRecord.table_name == table,
                    DynamicRecord.natural_key.in_(natural_keys),
                )
                .all()
            )
            existing = {row.natural_key: row for row in rows if row.natural_key}
        elif hashes:
            rows = (
                self.db.query(DynamicRecord)
                .filter(
                    DynamicRecord.source_id == source_id,
                    DynamicRecord.table_name == table,
                    DynamicRecord.content_hash.in_(hashes),
                )
                .all()
            )
            existing = {row.content_hash: row for row in rows}

        inserted = updated = duplicated = 0
        for safe, key_value, digest in prepared:
            lookup = key_value if key_value is not None else digest
            current = existing.get(lookup)
            if current is not None:
                if self.policy == "skip":
                    duplicated += 1
                    continue
                if self.policy == "flag":
                    current.duplicate_flag = True
                    duplicated += 1
                    continue
                if self.policy in {"update", "upsert"}:
                    current.data = safe
                    current.content_hash = digest
                    flag_modified(current, "data")
                    updated += 1
                    continue
            if self.policy == "update":
                continue
            created = DynamicRecord(
                source_id=source_id,
                table_name=table,
                data=safe,
                content_hash=digest,
                natural_key=key_value,
                duplicate_flag=False,
            )
            self.db.add(created)
            existing[lookup] = created
            inserted += 1
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return inserted, updated, duplicated
