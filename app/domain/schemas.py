from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

DedupPolicy = Literal["skip", "update", "upsert", "flag"]
ExtractMode = Literal["full", "delta"]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    type: str = Field(min_length=1, max_length=50)
    config: dict[str, Any]
    canonical_mapping: dict[str, dict[str, str]] = Field(default_factory=dict)
    dedup_key: list[str] = Field(default_factory=list)
    dedup_policy: DedupPolicy = "upsert"
    schedule: str | None = None
    incremental_column: str | None = None
    contains_pii: bool = False

    @field_validator("dedup_key")
    @classmethod
    def dedup_keys_safe(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item or len(item) > 100:
                raise ValueError("Clave de deduplicación inválida")
        return value


class DataSourceUpdate(BaseModel):
    config: dict[str, Any] | None = None
    canonical_mapping: dict[str, dict[str, str]] | None = None
    dedup_key: list[str] | None = None
    dedup_policy: DedupPolicy | None = None
    schedule: str | None = None
    incremental_column: str | None = None
    contains_pii: bool | None = None
    active: bool | None = None


class DataSourceOut(BaseModel):
    id: int
    name: str
    type: str
    config: dict[str, Any]
    canonical_mapping: dict[str, Any]
    dedup_key: list[str]
    dedup_policy: str
    schedule: str | None = None
    incremental_column: str | None = None
    contains_pii: bool = False
    active: bool
    discovered_schema: dict[str, Any] | None = None
    model_config = ConfigDict(from_attributes=True)


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False


class RelationInfo(BaseModel):
    column: str
    referred_table: str
    referred_column: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    relations: list[RelationInfo] = Field(default_factory=list)


class SourceSchema(BaseModel):
    tables: list[TableInfo]
    diff: dict[str, Any] | None = None


class JobOut(BaseModel):
    id: int
    source_id: int
    status: str
    mode: str
    started_at: datetime | None
    finished_at: datetime | None
    rows_extracted: int
    rows_inserted: int
    rows_updated: int
    rows_duplicated: int
    errors_count: int
    bytes_read: int
    http_status: int | None
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(from_attributes=True)


class QueryFilter(BaseModel):
    field: str
    op: Literal["eq", "ne", "gt", "lt", "like", "in"] = "eq"
    value: Any


class QueryRequest(BaseModel):
    table: str
    columns: list[str] | None = None
    filters: list[QueryFilter] = Field(default_factory=list)
    order_by: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ErrorOut(BaseModel):
    id: int
    job_id: int | None
    source_name: str | None
    stage: str
    message: str
    stack_trace: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AuditOut(BaseModel):
    id: int
    username: str | None
    action: str
    resource: str
    detail: dict[str, Any] | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
