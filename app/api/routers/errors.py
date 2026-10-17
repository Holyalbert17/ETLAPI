from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.domain.models import AuditLog, ErrorLog, User
from app.domain.schemas import AuditOut, ErrorOut

router = APIRouter(tags=["Errors"])


@router.get("/errors", response_model=list[ErrorOut])
def list_errors(
    job_id: int | None = None,
    stage: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(ErrorLog)
    if job_id is not None:
        query = query.filter_by(job_id=job_id)
    if stage:
        query = query.filter_by(stage=stage)
    rows = query.order_by(ErrorLog.id.desc()).limit(200).all()
    admin = user.role == "admin"
    result = []
    for row in rows:
        item = ErrorOut.model_validate(row)
        if not admin:
            item.stack_trace = None
            item.payload = None
        result.append(item)
    return result


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if _.role != "admin":
        raise HTTPException(403, "Se requiere rol admin")
    return db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
