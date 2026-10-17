import json

import typer
from sqlalchemy.orm import Session

from app.api.presenters import present_source
from app.config import settings
from app.database import SessionLocal
from app.domain.models import DataSource, ExtractionJob
from app.logging_config import setup_logging
from app.services.factory import list_extractors
from app.services.jobs import create_extraction_job
from app.worker import run_extraction_task

cli = typer.Typer(help="Operaciones administrativas del extractor de datos")
sources_cli = typer.Typer(help="Orígenes de datos")
jobs_cli = typer.Typer(help="Ejecuciones")
cli.add_typer(sources_cli, name="sources")
cli.add_typer(jobs_cli, name="jobs")


def _session() -> Session:
    return SessionLocal()


@sources_cli.command("types")
def source_types() -> None:
    typer.echo(json.dumps(list_extractors(), ensure_ascii=False))


@sources_cli.command("list")
def source_list() -> None:
    db = _session()
    try:
        rows = db.query(DataSource).order_by(DataSource.id).all()
        payload = [present_source(row).model_dump(mode="json") for row in rows]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


@jobs_cli.command("list")
def job_list() -> None:
    db = _session()
    try:
        rows = db.query(ExtractionJob).order_by(ExtractionJob.id.desc()).limit(20).all()
        payload = [
            {
                "id": row.id,
                "source_id": row.source_id,
                "status": row.status,
                "rows_extracted": row.rows_extracted,
                "errors_count": row.errors_count,
            }
            for row in rows
        ]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        db.close()


@cli.command("extract")
def extract(source_id: int, mode: str = "full") -> None:
    if mode not in {"full", "delta"}:
        raise typer.BadParameter("mode debe ser full o delta")
    db = _session()
    try:
        source = db.get(DataSource, source_id)
        if source is None:
            typer.echo("Origen no encontrado")
            raise typer.Exit(code=1)
        job = create_extraction_job(db, source, mode=mode)
        job_id = job.id
    finally:
        db.close()
    run_extraction_task(source_id, job_id, mode)
    typer.echo(json.dumps({"job_id": job_id, "mode": mode}))


def main() -> None:
    setup_logging(settings.LOG_LEVEL)
    cli()


if __name__ == "__main__":
    main()
