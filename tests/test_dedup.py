from app.adapters.loaders.postgres_loader import PostgresLoader
from app.domain.models import DataSource, DynamicRecord


def _source(db, name, policy="upsert"):
    source = DataSource(name=name, type="csv", config={"path": "x"}, dedup_key=["id"], dedup_policy=policy)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def test_upsert_updates_existing_row(db):
    source = _source(db, "dedup_upsert")
    loader = PostgresLoader(db, "upsert")
    inserted, updated, duplicated = loader.upsert(source.id, "t", [{"id": "1", "v": "a"}], ["id"])
    assert (inserted, updated, duplicated) == (1, 0, 0)
    inserted, updated, duplicated = loader.upsert(source.id, "t", [{"id": "1", "v": "b"}], ["id"])
    assert updated == 1
    row = db.query(DynamicRecord).filter_by(source_id=source.id, table_name="t").one()
    assert row.data["v"] == "b"


def test_skip_flag_update_and_hash(db):
    source = _source(db, "dedup_policies")
    loader = PostgresLoader(db, "skip")
    loader.upsert(source.id, "t", [{"id": "1", "v": "a"}], ["id"])
    inserted, updated, duplicated = loader.upsert(source.id, "t", [{"id": "1", "v": "z"}], ["id"])
    assert duplicated == 1 and inserted == 0
    row = db.query(DynamicRecord).filter_by(source_id=source.id, natural_key="1").one()
    assert row.data["v"] == "a"

    loader.policy = "flag"
    _, _, duplicated = loader.upsert(source.id, "t", [{"id": "1", "v": "c"}], ["id"])
    assert duplicated == 1
    db.refresh(row)
    assert row.duplicate_flag is True
    assert row.data["v"] == "a"

    loader.policy = "update"
    inserted, updated, _ = loader.upsert(source.id, "t", [{"id": "1", "v": "d"}, {"id": "9", "v": "new"}], ["id"])
    assert updated == 1
    assert inserted == 0
    db.refresh(row)
    assert row.data["v"] == "d"
    assert db.query(DynamicRecord).filter_by(source_id=source.id, natural_key="9").first() is None

    loader.policy = "skip"
    loader.upsert(source.id, "h", [{"a": 1}], [])
    _, _, duplicated = loader.upsert(source.id, "h", [{"a": 1}], [])
    assert duplicated == 1


def test_duplicate_inside_same_batch(db):
    source = _source(db, "dedup_batch")
    loader = PostgresLoader(db, "upsert")
    inserted, updated, _ = loader.upsert(
        source.id,
        "t",
        [{"id": "1", "v": "a"}, {"id": "1", "v": "b"}],
        ["id"],
    )
    assert inserted == 1
    assert updated == 1
    row = db.query(DynamicRecord).filter_by(source_id=source.id, table_name="t").one()
    assert row.data["v"] == "b"
