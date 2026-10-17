"""Migración inicial del extractor."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("canonical_mapping", sa.JSON(), nullable=False),
        sa.Column("dedup_key", sa.JSON(), nullable=False),
        sa.Column("dedup_policy", sa.String(20), nullable=False, server_default="upsert"),
        sa.Column("schedule", sa.String(80), nullable=True),
        sa.Column("incremental_column", sa.String(100), nullable=True),
        sa.Column("contains_pii", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("discovered_schema", sa.JSON(), nullable=True),
        sa.Column("watermarks", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_data_sources_name", "data_sources", ["name"], unique=True)
    op.create_index("ix_data_sources_type", "data_sources", ["type"])

    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="full"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extraction_jobs_source_id", "extraction_jobs", ["source_id"])
    op.create_index("ix_extraction_jobs_status", "extraction_jobs", ["status"])

    op.create_table(
        "error_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_name", sa.String(100), nullable=True),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_error_logs_job_id", "error_logs", ["job_id"])
    op.create_index("ix_error_logs_stage", "error_logs", ["stage"])

    op.create_table(
        "dynamic_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("natural_key", sa.String(512), nullable=True),
        sa.Column("duplicate_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dynamic_records_source_id", "dynamic_records", ["source_id"])
    op.create_index("ix_dynamic_records_table_name", "dynamic_records", ["table_name"])
    op.create_index("ix_dynamic_records_content_hash", "dynamic_records", ["content_hash"])
    op.create_index("ix_dynamic_records_natural_key", "dynamic_records", ["natural_key"])

    op.create_table(
        "raw_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("extraction_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_raw_records_source_id", "raw_records", ["source_id"])
    op.create_index("ix_raw_records_job_id", "raw_records", ["job_id"])
    op.create_index("ix_raw_records_table_name", "raw_records", ["table_name"])

    op.create_table(
        "schema_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schema_snapshots_source_id", "schema_snapshots", ["source_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(200), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_username", "audit_logs", ["username"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("schema_snapshots")
    op.drop_table("raw_records")
    op.drop_table("dynamic_records")
    op.drop_table("error_logs")
    op.drop_table("extraction_jobs")
    op.drop_table("data_sources")
    op.drop_table("users")
