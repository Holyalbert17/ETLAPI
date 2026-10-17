from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.domain.models import DataSource, SchemaSnapshot
from app.domain.schemas import SourceSchema
from app.services.schema_diff import diff_schemas


class SchemaDiscoveryService:
    def __init__(self, db: Session):
        self.db = db

    def capture(self, source: DataSource, schema: SourceSchema) -> dict:
        current = {"tables": [table.model_dump() for table in schema.tables]}
        previous = source.discovered_schema
        diff = diff_schemas(previous, current)
        if previous is None or diff["changed"]:
            self.db.add(
                SchemaSnapshot(source_id=source.id, schema_json=current, diff_json=diff)
            )
        source.discovered_schema = current
        flag_modified(source, "discovered_schema")
        self.db.commit()
        return diff
