import json
import logging

import pytest
from app.config import settings
from app.security import decrypt_secrets, encrypt_secrets, mask_secrets, redact
from app.services.dedup import advance_watermark, content_hash, natural_key
from app.services.factory import register_extractor
from app.services.identifiers import UnsafeIdentifier, quote_ident
from app.services.mapping import apply_mapping
from app.services.normalizer import normalize_record
from app.services.schema_diff import diff_schemas
from app.services.validator import ValidationError, validate_record


def test_encrypt_mask_and_redact():
    config = {"dsn": "postgresql://user:s3cret@localhost/db", "schema": "public", "headers": {"authorization": "Bearer abc"}}
    encrypted = encrypt_secrets(config)
    assert encrypted["dsn"].startswith("enc:v1:")
    assert encrypted["headers"]["authorization"].startswith("enc:v1:")
    assert decrypt_secrets(encrypted)["dsn"] == config["dsn"]
    assert mask_secrets(encrypted)["dsn"] == "***"
    assert mask_secrets(encrypted)["schema"] == "public"
    assert "s3cret" not in redact("fallo postgresql://user:s3cret@localhost/db")
    assert content_hash({"b": 1, "a": 2}) == content_hash({"a": 2, "b": 1})
    assert natural_key({"id": 1, "name": "Ana"}, ["id", "name"]) == "1|Ana"


def test_normalize_map_and_validate():
    record = normalize_record(
        {"nombre": " Ana ", "alta": "2024-03-01", "precio": "$ 1.234,50", "vacio": "  ", "raw": b"caf\xc3\xa9"}
    )
    assert record["nombre"] == "Ana"
    assert record["alta"] == "2024-03-01"
    assert record["precio"] == "1234.50"
    assert record["vacio"] is None
    assert record["raw"] == "café"
    mapped = apply_mapping(record, {"nombre": "full_name"})
    assert mapped["full_name"] == "Ana"
    assert "nombre" not in mapped
    validate_record(mapped, required_fields=["full_name"], constraints={"precio": {"format": "number", "min": 0}})
    with pytest.raises(ValidationError):
        validate_record({"email": "nope"}, constraints={"email": {"format": "email"}})
    with pytest.raises(ValidationError):
        validate_record({"age": 200}, constraints={"age": {"min": 0, "max": 120}})


def test_schema_diff_and_watermark():
    previous = {"tables": [{"name": "clientes", "columns": [{"name": "id", "type": "int"}]}]}
    current = {
        "tables": [
            {
                "name": "clientes",
                "columns": [{"name": "id", "type": "text"}, {"name": "email", "type": "text"}],
            },
            {"name": "pedidos", "columns": [{"name": "id", "type": "int"}]},
        ]
    }
    diff = diff_schemas(previous, current)
    assert diff["changed"] is True
    assert diff["added_tables"] == ["pedidos"]
    assert diff["added_columns"]["clientes"] == ["email"]
    assert diff["type_changes"]["clientes"][0]["column"] == "id"
    assert advance_watermark("9", ["10", "8"]) == "10"
    assert advance_watermark(None, ["2024-01-01", "2024-05-01"]) == "2024-05-01"


def test_rejects_unsafe_identifiers():
    with pytest.raises(UnsafeIdentifier):
        quote_ident("id;drop")
    with pytest.raises(TypeError):
        register_extractor("malo", dict)


def test_json_formatter_includes_correlation():
    from app.context import correlation_id_ctx
    from app.logging_config import JSONFormatter

    token = correlation_id_ctx.set("corr-1")
    try:
        record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hola", (), None)
        record.job_id = 7
        payload = json.loads(JSONFormatter().format(record))
    finally:
        correlation_id_ctx.reset(token)
    assert payload["message"] == "hola"
    assert payload["correlation_id"] == "corr-1"
    assert payload["job_id"] == 7


def test_webhook_notification(monkeypatch):
    from app.services.notifier import notify_critical

    calls = {}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout

    monkeypatch.setattr(settings, "ERROR_WEBHOOK_URL", "http://hooks.test/error")
    monkeypatch.setattr("app.services.notifier.httpx.post", fake_post)
    notify_critical("fallo crítico", {"job_id": 4})
    assert calls["url"] == "http://hooks.test/error"
    assert calls["json"]["job_id"] == 4


def test_schedule_parser():
    from app.scheduler import parse_trigger, validate_schedule

    parse_trigger("0 */6 * * *")
    parse_trigger("@every 300s")
    with pytest.raises(ValueError):
        validate_schedule("@every mañana")


def test_dispatch_uses_redis_when_configured(monkeypatch):
    import redis
    import rq
    from app.queueing import dispatch_extraction

    calls = {}

    class FakeQueue:
        def __init__(self, name, connection):
            calls["name"] = name
            calls["connection"] = connection

        def enqueue(self, path, *args):
            calls["path"] = path
            calls["args"] = args

    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6390/0")
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda url: {"url": url}))
    monkeypatch.setattr(rq, "Queue", FakeQueue)
    dispatch_extraction(3, 8, "delta")
    assert calls["name"] == "extraction"
    assert calls["path"] == "app.worker.run_extraction_task"
    assert calls["args"] == (3, 8, "delta")


def test_cli_lists_and_missing_source():
    from app.cli import cli
    from typer.testing import CliRunner

    runner = CliRunner()
    assert runner.invoke(cli, ["sources", "types"]).exit_code == 0
    assert runner.invoke(cli, ["sources", "list"]).exit_code == 0
    listed = runner.invoke(cli, ["jobs", "list"])
    assert listed.exit_code == 0
    missing = runner.invoke(cli, ["extract", "999999"])
    assert missing.exit_code == 1


def test_bootstrap_admin(monkeypatch, db):
    from app.bootstrap import ensure_admin
    from app.domain.models import User

    monkeypatch.setattr(settings, "ADMIN_USERNAME", "bootadmin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "boot-secret")
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "boot@example.com")
    ensure_admin()
    ensure_admin()
    rows = db.query(User).filter_by(username="bootadmin").all()
    db.expire_all()
    rows = db.query(User).filter_by(username="bootadmin").all()
    assert len(rows) == 1
    assert rows[0].role == "admin"


def test_connect_retries_then_fails(client, admin_headers):
    from app.domain.schemas import SourceSchema
    from app.ports.base_extractor import BaseExtractor

    class DownExtractor(BaseExtractor):
        calls = 0

        def connect(self):
            DownExtractor.calls += 1
            raise ConnectionError("postgresql://user:secret@db/nope")

        def close(self):
            return None

        def discover_schema(self) -> SourceSchema:
            return SourceSchema(tables=[])

        def extract(self, table, batch_size=500, checkpoint=None):
            yield {}

    DownExtractor.calls = 0
    register_extractor("down", DownExtractor)
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"name": "down_src", "type": "down", "config": {}},
    )
    assert created.status_code == 201
    started = client.post(f"/api/v1/extract/{created.json()['id']}", headers=admin_headers)
    job = client.get(f"/api/v1/jobs/{started.json()['id']}", headers=admin_headers).json()
    assert job["status"] == "failed"
    assert DownExtractor.calls == 2
    errors = client.get(f"/api/v1/errors?job_id={job['id']}", headers=admin_headers).json()
    assert errors
    assert "secret" not in errors[0]["message"]


def test_user_does_not_see_stacktrace(client, user_headers, admin_headers):
    errors = client.get("/api/v1/errors", headers=user_headers)
    assert errors.status_code == 200
    if errors.json():
        assert errors.json()[0]["stack_trace"] is None
    audit = client.get("/api/v1/audit", headers=user_headers)
    assert audit.status_code == 403
    assert client.get("/api/v1/audit", headers=admin_headers).status_code == 200


def test_scheduler_sync_and_tick(client, admin_headers, tmp_path, monkeypatch, db):
    from app.domain.models import DataSource
    from app.scheduler import _scheduled, scheduler, sync_schedules

    path = tmp_path / "sched.csv"
    path.write_text("id,nombre\n1,Ana\n", encoding="utf-8")
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"name": "sched_src", "type": "csv", "config": {"path": str(path)}, "dedup_key": ["id"]},
    )
    source_id = created.json()["id"]
    source = db.get(DataSource, source_id)
    source.schedule = "0 0 * * *"
    db.commit()
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", True)
    try:
        sync_schedules(db)
        assert scheduler.get_job(f"src-{source_id}") is not None
        source.schedule = "esto no es cron"
        db.commit()
        sync_schedules(db)
        _scheduled(source_id)
    finally:
        scheduler.remove_all_jobs()
        monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
    job = client.get("/api/v1/jobs?source_id=" + str(source_id), headers=admin_headers)
    assert job.status_code == 200
    assert any(item["status"] == "success" for item in job.json())
