from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.adapters.repositories.sql_repository import write_audit
from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.domain.models import ExtractionJob, User
from app.domain.schemas import ExtractMode, JobOut
from app.queueing import dispatch_extraction
from app.services.jobs import create_extraction_job

router = APIRouter(tags=["Jobs"])


@router.post("/extract/{source_id}", response_model=JobOut, status_code=202)
def trigger_extraction(
    source_id: int,
    background: BackgroundTasks,
    mode: ExtractMode = Query("full"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    from app.domain.models import DataSource

    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "Origen no encontrado")
    if not source.active:
        raise HTTPException(409, "El origen está inactivo")
    job = create_extraction_job(db, source, mode=mode)
    write_audit(
        db,
        username=user.username,
        action="extract",
        resource=f"source:{source.id}",
        detail={"job_id": job.id, "mode": mode},
    )
    dispatch_extraction(source.id, job.id, mode, background)
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    source_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(ExtractionJob).order_by(ExtractionJob.id.desc())
    if source_id is not None:
        query = query.filter_by(source_id=source_id)
    return query.limit(100).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    job = db.get(ExtractionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job no encontrado")
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(
    job_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    from app.domain.models import DataSource

    old = db.get(ExtractionJob, job_id)
    if old is None:
        raise HTTPException(404, "Job no encontrado")
    if old.status not in {"failed", "partial"}:
        raise HTTPException(409, "Solo se reintentan jobs fallidos o parciales")
    source = db.get(DataSource, old.source_id)
    if source is None:
        raise HTTPException(404, "Origen no encontrado")
    job = create_extraction_job(db, source, mode=old.mode, resume=old)
    write_audit(
        db,
        username=user.username,
        action="job_retry",
        resource=f"job:{old.id}",
        detail={"new_job_id": job.id},
    )
    dispatch_extraction(source.id, job.id, job.mode, background)
    return job
