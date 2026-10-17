import logging
import time

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from tenacity import retry, stop_after_attempt, wait_exponential, wait_none

from app.adapters.loaders.postgres_loader import PostgresLoader
from app.adapters.repositories.sql_repository import SqlRepository
from app.config import settings
from app.domain.models import DataSource, ExtractionJob, utcnow
from app.metrics import (
    ACTIVE_JOBS,
    ERRORS_TOTAL,
    EXTRACTION_DURATION,
    EXTRACTIONS_TOTAL,
    ROWS_DUPLICATED,
    ROWS_EXTRACTED,
    ROWS_INSERTED,
    ROWS_UPDATED,
)
from app.security import decrypt_secrets, redact
from app.services.dedup import advance_watermark
from app.services.factory import get_extractor
from app.services.mapping import apply_mapping
from app.services.normalizer import normalize_record, to_jsonable
from app.services.notifier import notify_critical
from app.services.schema_discovery import SchemaDiscoveryService
from app.services.validator import ValidationError, validate_record

logger = logging.getLogger(__name__)


class ExtractorService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SqlRepository(db)

    def run(self, source_id: int, job_id: int, mode: str = "full") -> ExtractionJob | None:
        job = self.db.get(ExtractionJob, job_id)
        source = self.db.get(DataSource, source_id)
        if job is None:
            return None
        if source is None or not source.active:
            job.status = "failed"
            job.finished_at = utcnow()
            job.errors_count = (job.errors_count or 0) + 1
            self.db.commit()
            return job

        job.status = "running"
        job.mode = mode or job.mode or "full"
        job.started_at = utcnow()
        self.db.commit()

        ACTIVE_JOBS.inc()
        started = time.perf_counter()
        extractor = None
        final_status = "success"
        totals = {
            "extracted": job.rows_extracted or 0,
            "inserted": job.rows_inserted or 0,
            "updated": job.rows_updated or 0,
            "duplicated": job.rows_duplicated or 0,
            "errors": job.errors_count or 0,
        }
        try:
            runtime = decrypt_secrets(dict(source.config or {}))
            if source.incremental_column:
                runtime["incremental_column"] = source.incremental_column
            extractor = get_extractor(source.type, runtime)
            self._call_with_retry(extractor.connect)
            schema = extractor.discover_schema()
            SchemaDiscoveryService(self.db).capture(source, schema)
            source = self.db.get(DataSource, source_id)
            job = self.db.get(ExtractionJob, job_id)
            loader = PostgresLoader(self.db, dedup_policy=source.dedup_policy)
            checkpoint = dict(job.checkpoint or {})
            done = list(checkpoint.get("done") or [])
            watermarks = dict(checkpoint.get("watermarks") or source.watermarks or {})

            for table in schema.tables:
                if table.name in done:
                    continue
                self._extract_table(
                    source=source,
                    job_id=job.id,
                    extractor=extractor,
                    loader=loader,
                    table_name=table.name,
                    mode=job.mode,
                    done=done,
                    watermarks=watermarks,
                    totals=totals,
                )

            source = self.db.get(DataSource, source_id)
            source.watermarks = watermarks
            flag_modified(source, "watermarks")
            final_status = "partial" if totals["errors"] else "success"
            self._write_progress(job_id, totals, final_status, done, watermarks, table=None, skip=0)
        except Exception as exc:
            self.db.rollback()
            final_status = "failed"
            totals["errors"] += 1
            job = self.db.get(ExtractionJob, job_id)
            source = self.db.get(DataSource, source_id)
            source_name = source.name if source is not None else str(source_id)
            if job is not None:
                job.status = "failed"
                job.errors_count = totals["errors"]
                self.db.commit()
            self.repo.log_error(job_id, "extraction", exc, source_name=source_name)
            ERRORS_TOTAL.labels(source=source_name, stage="extraction").inc()
            logger.error(redact(f"Fallo en extracción de {source_name}: {exc}"))
            notify_critical(
                f"Extracción fallida para {source_name}",
                {"source": source_name, "job_id": job_id, "stage": "extraction"},
            )
        finally:
            if extractor is not None:
                try:
                    extractor.close()
                except Exception:
                    logger.warning("No se pudo cerrar el extractor")
            job = self.db.get(ExtractionJob, job_id)
            if job is not None:
                job.status = final_status if job.status != "failed" else "failed"
                job.finished_at = utcnow()
                job.rows_extracted = totals["extracted"]
                job.rows_inserted = totals["inserted"]
                job.rows_updated = totals["updated"]
                job.rows_duplicated = totals["duplicated"]
                job.errors_count = totals["errors"]
                if extractor is not None:
                    job.bytes_read = extractor.bytes_read
                    job.http_status = extractor.last_http_status
                self.db.commit()
            ACTIVE_JOBS.dec()
            label = source.name if source is not None else str(source_id)
            EXTRACTIONS_TOTAL.labels(source=label, status=final_status).inc()
            EXTRACTION_DURATION.labels(source=label).observe(time.perf_counter() - started)
        return self.db.get(ExtractionJob, job_id)

    def _extract_table(
        self,
        *,
        source: DataSource,
        job_id: int,
        extractor,
        loader: PostgresLoader,
        table_name: str,
        mode: str,
        done: list[str],
        watermarks: dict,
        totals: dict,
    ) -> None:
        job = self.db.get(ExtractionJob, job_id)
        checkpoint = dict(job.checkpoint or {})
        start_skip = int(checkpoint.get("skip") or 0) if checkpoint.get("table") == table_name else 0
        watermark = watermarks.get(table_name) if mode == "delta" and source.incremental_column else None
        batch_size = max(1, settings.BATCH_SIZE)
        mapping = (source.canonical_mapping or {}).get(table_name) or {}
        stored_config = source.config or {}
        required = list(stored_config.get("required_fields") or [])
        constraints = dict(stored_config.get("constraints") or {})
        buffer: list[dict] = []
        raw_buffer: list[dict] = []
        produced = 0
        committed = start_skip
        seen_marks: list = []
        logger.info(
            "Extrayendo %s.%s",
            source.name,
            table_name,
            extra={"source_id": source.id, "job_id": job_id, "stage": "extract"},
        )
        try:
            for raw in extractor.extract(
                table_name,
                batch_size,
                {"skip": start_skip, "watermark": watermark},
            ):
                raw_safe = to_jsonable(raw)
                raw_buffer.append(raw_safe)
                produced += 1
                totals["extracted"] += 1
                ROWS_EXTRACTED.labels(source=source.name, table=table_name).inc()
                if source.incremental_column and source.incremental_column in raw_safe:
                    seen_marks.append(raw_safe.get(source.incremental_column))
                try:
                    record = normalize_record(apply_mapping(raw_safe, mapping))
                    validate_record(record, required_fields=required, constraints=constraints)
                except ValidationError as exc:
                    totals["errors"] += 1
                    ERRORS_TOTAL.labels(source=source.name, stage="validation").inc()
                    self.repo.log_error(
                        job_id,
                        "validation",
                        exc,
                        payload=raw_safe,
                        source_name=source.name,
                    )
                    continue
                buffer.append(record)
                if len(raw_buffer) >= batch_size:
                    self._flush(loader, source, job_id, table_name, raw_buffer, buffer, totals)
                    committed = start_skip + produced
                    raw_buffer = []
                    buffer = []
                    self._write_progress(
                        job_id, totals, "running", done, watermarks, table=table_name, skip=committed
                    )
            if raw_buffer:
                self._flush(loader, source, job_id, table_name, raw_buffer, buffer, totals)
                committed = start_skip + produced
            watermarks[table_name] = advance_watermark(watermarks.get(table_name), seen_marks)
            done.append(table_name)
            self._write_progress(job_id, totals, "running", done, watermarks, table=None, skip=0)
        except Exception:
            self._write_progress(
                job_id,
                totals,
                "running",
                done,
                watermarks,
                table=table_name,
                skip=committed,
            )
            raise

    def _flush(self, loader, source, job_id, table_name, raw_buffer, buffer, totals) -> None:
        def _op():
            loader.store_raw(source.id, job_id, table_name, raw_buffer)
            if not buffer:
                self.db.commit()
                return 0, 0, 0
            return loader.upsert(source.id, table_name, buffer, list(source.dedup_key or []))

        inserted, updated, duplicated = self._call_with_retry(_op)
        totals["inserted"] += inserted
        totals["updated"] += updated
        totals["duplicated"] += duplicated
        if inserted:
            ROWS_INSERTED.labels(source=source.name, table=table_name).inc(inserted)
        if updated:
            ROWS_UPDATED.labels(source=source.name, table=table_name).inc(updated)
        if duplicated:
            ROWS_DUPLICATED.labels(source=source.name, table=table_name).inc(duplicated)

    def _write_progress(self, job_id, totals, status, done, watermarks, *, table, skip) -> None:
        job = self.db.get(ExtractionJob, job_id)
        if job is None:
            return
        job.status = status
        job.rows_extracted = totals["extracted"]
        job.rows_inserted = totals["inserted"]
        job.rows_updated = totals["updated"]
        job.rows_duplicated = totals["duplicated"]
        job.errors_count = totals["errors"]
        job.checkpoint = {
            "table": table,
            "skip": skip,
            "done": list(done),
            "watermarks": dict(watermarks),
        }
        flag_modified(job, "checkpoint")
        self.db.commit()

    @staticmethod
    def _call_with_retry(func):
        wait = (
            wait_none()
            if settings.RETRY_BACKOFF <= 0
            else wait_exponential(
                multiplier=settings.RETRY_BACKOFF,
                min=settings.RETRY_BACKOFF,
                max=30,
            )
        )
        return retry(
            stop=stop_after_attempt(max(1, settings.MAX_RETRIES)),
            wait=wait,
            reraise=True,
        )(func)()
