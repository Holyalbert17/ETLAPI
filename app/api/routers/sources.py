from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.adapters.repositories.sql_repository import SqlRepository, write_audit
from app.api.deps import get_current_user, require_admin
from app.api.presenters import present_source
from app.database import get_db
from app.domain.models import DataSource, User
from app.domain.schemas import DataSourceCreate, DataSourceOut, DataSourceUpdate
from app.scheduler import sync_schedules, validate_schedule
from app.security import encrypt_secrets, merge_config
from app.services.factory import REGISTRY, list_extractors

router = APIRouter(prefix="/sources", tags=["Sources"])


def _check_type(source_type: str) -> None:
    if source_type not in REGISTRY:
        raise HTTPException(
            400,
            f"Tipo no soportado: {source_type}. Disponibles: {', '.join(list_extractors())}",
        )


@router.get("/types")
def available_types(_: User = Depends(get_current_user)):
    return {"types": list_extractors()}


@router.get("", response_model=list[DataSourceOut])
def list_sources(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(DataSource).order_by(DataSource.id).all()
    return [present_source(row) for row in rows]


@router.post("", response_model=DataSourceOut, status_code=201)
def create_source(
    payload: DataSourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    _check_type(payload.type)
    if db.query(DataSource).filter_by(name=payload.name).first():
        raise HTTPException(409, "Ya existe un origen con ese nombre")
    try:
        validate_schedule(payload.schedule)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    source = DataSource(
        name=payload.name,
        type=payload.type,
        config=encrypt_secrets(payload.config),
        canonical_mapping=payload.canonical_mapping,
        dedup_key=payload.dedup_key,
        dedup_policy=payload.dedup_policy,
        schedule=payload.schedule,
        incremental_column=payload.incremental_column,
        contains_pii=payload.contains_pii,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    write_audit(
        db,
        username=user.username,
        action="source_create",
        resource=f"source:{source.id}",
        detail={"name": source.name, "type": source.type},
    )
    sync_schedules(db)
    return present_source(source)


@router.get("/{source_id}", response_model=DataSourceOut)
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "No encontrado")
    return present_source(source)


@router.patch("/{source_id}", response_model=DataSourceOut)
def update_source(
    source_id: int,
    payload: DataSourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "No encontrado")
    data = payload.model_dump(exclude_unset=True)
    if "schedule" in data:
        try:
            validate_schedule(data["schedule"])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        source.schedule = data["schedule"]
    if "config" in data and data["config"] is not None:
        merged = merge_config(dict(source.config or {}), data["config"])
        source.config = encrypt_secrets(merged)
        flag_modified(source, "config")
    if "canonical_mapping" in data and data["canonical_mapping"] is not None:
        source.canonical_mapping = data["canonical_mapping"]
    if "dedup_key" in data and data["dedup_key"] is not None:
        source.dedup_key = data["dedup_key"]
    if "dedup_policy" in data and data["dedup_policy"] is not None:
        source.dedup_policy = data["dedup_policy"]
    if "incremental_column" in data:
        source.incremental_column = data["incremental_column"]
    if "contains_pii" in data and data["contains_pii"] is not None:
        source.contains_pii = data["contains_pii"]
    if "active" in data and data["active"] is not None:
        source.active = data["active"]
    db.commit()
    db.refresh(source)
    write_audit(
        db,
        username=user.username,
        action="source_update",
        resource=f"source:{source.id}",
        detail={"fields": sorted(data)},
    )
    sync_schedules(db)
    return present_source(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "No encontrado")
    name = source.name
    write_audit(
        db,
        username=user.username,
        action="source_delete",
        resource=f"source:{source_id}",
        detail={"name": name},
    )
    SqlRepository(db).delete_source(source)
    sync_schedules(db)
