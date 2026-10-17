from sqlalchemy.orm import Session

from app.domain.models import DataSource, ExtractionJob


def create_extraction_job(
    db: Session,
    source: DataSource,
    *,
    mode: str = "full",
    resume: ExtractionJob | None = None,
) -> ExtractionJob:
    if resume is not None:
        checkpoint = dict(resume.checkpoint or {})
        mode = resume.mode or mode
    elif mode == "delta":
        checkpoint = {
            "watermarks": dict(source.watermarks or {}),
            "done": [],
            "skip": 0,
            "table": None,
        }
    else:
        checkpoint = {}
    job = ExtractionJob(
        source_id=source.id,
        status="pending",
        mode=mode,
        checkpoint=checkpoint,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
