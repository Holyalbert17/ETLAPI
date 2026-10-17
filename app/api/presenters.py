from app.domain.models import DataSource
from app.domain.schemas import DataSourceOut
from app.security import mask_secrets


def present_source(source: DataSource) -> DataSourceOut:
    return DataSourceOut(
        id=source.id,
        name=source.name,
        type=source.type,
        config=mask_secrets(dict(source.config or {})),
        canonical_mapping=dict(source.canonical_mapping or {}),
        dedup_key=list(source.dedup_key or []),
        dedup_policy=source.dedup_policy,
        schedule=source.schedule,
        incremental_column=source.incremental_column,
        contains_pii=bool(source.contains_pii),
        active=bool(source.active),
        discovered_schema=source.discovered_schema,
    )
