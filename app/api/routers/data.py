from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.adapters.repositories.sql_repository import SqlRepository, write_audit
from app.api.deps import get_current_user
from app.database import get_db
from app.domain.models import User
from app.domain.schemas import QueryRequest
from app.services.identifiers import UnsafeIdentifier

router = APIRouter(prefix="/data", tags=["Data"])


def _source_or_404(repo: SqlRepository, name: str):
    source = repo.get_source_by_name(name)
    if source is None:
        raise HTTPException(404, "Origen no encontrado")
    return source


@router.get("/{source_name}/tables")
def list_tables(
    source_name: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = SqlRepository(db)
    source = _source_or_404(repo, source_name)
    _audit_read(db, user, source)
    stored = []
    if source.discovered_schema:
        stored = [table["name"] for table in source.discovered_schema.get("tables", [])]
    loaded = repo.list_tables(source.id)
    names = sorted(set(stored) | set(loaded))
    return {"tables": names}


@router.get("/{source_name}/{table}")
def get_data(
    source_name: str,
    table: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    order_by: str | None = None,
    filter_expr: str | None = Query(None, alias="filter", description="Formato campo:valor"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = SqlRepository(db)
    source = _source_or_404(repo, source_name)
    filters = []
    if filter_expr:
        if ":" not in filter_expr:
            raise HTTPException(400, "El filtro debe tener formato campo:valor")
        field, value = filter_expr.split(":", 1)
        filters.append({"field": field, "op": "eq", "value": value})
    return _run_query(
        db,
        repo,
        source,
        user,
        table=table,
        columns=None,
        filters=filters,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )


@router.post("/{source_name}/query")
def query_data(
    source_name: str,
    payload: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = SqlRepository(db)
    source = _source_or_404(repo, source_name)
    filters = [item.model_dump() for item in payload.filters]
    return _run_query(
        db,
        repo,
        source,
        user,
        table=payload.table,
        columns=payload.columns,
        filters=filters,
        limit=payload.limit,
        offset=payload.offset,
        order_by=payload.order_by,
    )


def _run_query(db, repo, source, user, **kwargs):
    try:
        result = repo.query_dynamic(source, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except UnsafeIdentifier as exc:
        raise HTTPException(400, str(exc)) from exc
    _audit_read(db, user, source, table=kwargs.get("table"))
    return result


def _audit_read(db, user: User, source, table: str | None = None) -> None:
    if not source.contains_pii:
        return
    write_audit(
        db,
        username=user.username,
        action="data_read",
        resource=f"source:{source.id}",
        detail={"table": table, "pii": True},
    )
