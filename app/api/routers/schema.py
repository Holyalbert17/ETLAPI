from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.domain.models import DataSource, User
from app.domain.schemas import SourceSchema
from app.security import decrypt_secrets, redact
from app.services.factory import get_extractor
from app.services.schema_discovery import SchemaDiscoveryService

router = APIRouter(prefix="/sources", tags=["Schema"])


@router.get("/{source_id}/schema", response_model=SourceSchema)
def get_schema(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "No encontrado")
    runtime = decrypt_secrets(dict(source.config or {}))
    if source.incremental_column:
        runtime["incremental_column"] = source.incremental_column
    try:
        extractor = get_extractor(source.type, runtime)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        extractor.connect()
        schema = extractor.discover_schema()
    except Exception as exc:
        raise HTTPException(502, f"No se pudo introspectar el origen: {redact(str(exc))}") from exc
    finally:
        try:
            extractor.close()
        except Exception:
            pass
    diff = SchemaDiscoveryService(db).capture(source, schema)
    return SourceSchema(tables=schema.tables, diff=diff)
