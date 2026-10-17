import json
from types import SimpleNamespace

import pytest
from app.adapters.extractors.api_extractor import APIExtractor
from app.adapters.extractors.csv_extractor import CSVExtractor
from app.adapters.extractors.json_extractor import JSONExtractor
from app.adapters.extractors.mongodb_extractor import MongoDBExtractor
from app.adapters.extractors.postgres_extractor import PostgresExtractor
from app.adapters.extractors.web_extractor import WebExtractor
from app.domain.schemas import ColumnInfo, SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor
from app.services.factory import get_extractor, register_extractor
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base


class _Response:
    def __init__(self, text="", payload=None, status=200):
        self.text = text
        self.content = text.encode() if text else json.dumps(payload or {}).encode()
        self.status_code = status
        self.encoding = "utf-8"
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


def test_postgres_extractor_discovers_and_reads_delta(tmp_path):
    path = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    base = declarative_base()

    class People(base):
        __tablename__ = "people"
        id = Column(Integer, primary_key=True)
        name = Column(String)
        updated_at = Column(String)

    base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            People.__table__.insert(),
            [
                {"id": 1, "name": "Ana", "updated_at": "2024-01-01"},
                {"id": 2, "name": "Beto", "updated_at": "2024-06-01"},
            ],
        )
    extractor = PostgresExtractor(
        {
            "dsn": f"sqlite:///{path.as_posix()}",
            "schema": "main",
            "tables": ["people"],
            "incremental_column": "updated_at",
        }
    )
    extractor.connect()
    try:
        schema = extractor.discover_schema()
        assert schema.tables[0].name == "people"
        assert any(column.primary_key for column in schema.tables[0].columns)
        rows = list(
            extractor.extract("people", batch_size=1, checkpoint={"watermark": "2024-01-01", "skip": 0})
        )
    finally:
        extractor.close()
    assert [row["name"] for row in rows] == ["Beto"]

    missing = PostgresExtractor(
        {"dsn": f"sqlite:///{path.as_posix()}", "schema": "main", "tables": ["no_existe"]}
    )
    missing.connect()
    try:
        with pytest.raises(ValueError):
            missing.discover_schema()
    finally:
        missing.close()


def test_csv_and_json_extractors(tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,nombre\n1,Ana\n2,Beto\n", encoding="utf-8")
    csv_extractor = CSVExtractor({"path": str(csv_path)})
    csv_extractor.connect()
    assert csv_extractor.discover_schema().tables[0].columns[0].name == "id"
    assert len(list(csv_extractor.extract("default", checkpoint={"skip": 1}))) == 1

    json_path = tmp_path / "data.json"
    json_path.write_text(json.dumps({"items": [{"id": 1, "city": "CABA"}]}), encoding="utf-8")
    json_extractor = JSONExtractor({"path": str(json_path), "records_path": "items"})
    json_extractor.connect()
    schema = json_extractor.discover_schema()
    assert schema.tables[0].columns[0].name == "id"
    assert list(json_extractor.extract("default"))[0]["city"] == "CABA"


def test_web_extractor_follows_next_link():
    first = """
    <html><body>
      <article class="product_pod"><h3><a title="Libro">x</a></h3><p class="price">£51.77</p></article>
      <a class="next" href="page-2.html">next</a>
    </body></html>
    """
    second = """
    <html><body>
      <article class="product_pod"><h3><a title="Otro">x</a></h3><p class="price">£10.00</p></article>
    </body></html>
    """
    pages = {"http://books.test/": first, "http://books.test/page-2.html": second}

    class Session:
        headers: dict = {}

        def get(self, url, timeout=15):
            return _Response(text=pages[url])

        def close(self):
            return None

    extractor = WebExtractor(
        {
            "url": "http://books.test/",
            "item_selector": "article.product_pod",
            "fields": {"titulo": "h3 a::attr(title)", "precio": "p.price::text"},
            "next_selector": "a.next::attr(href)",
            "rate_limit": 0,
            "respect_robots": False,
            "max_pages": 5,
        }
    )
    extractor.connect()
    extractor.session = Session()
    rows = list(extractor.extract("default"))
    extractor.close()
    assert [row["titulo"] for row in rows] == ["Libro", "Otro"]
    assert rows[0]["precio"] == "£51.77"


def test_api_extractor_reads_data_path():
    class Session:
        headers: dict = {}

        def request(self, method, url, params=None, timeout=30):
            return _Response(payload={"results": [{"id": 1, "name": "A"}]})

        def close(self):
            return None

    extractor = APIExtractor(
        {
            "url": "http://api.test/items",
            "data_path": "results",
            "pagination": {"type": "page", "max_pages": 1, "size": 10},
        }
    )
    extractor.session = Session()
    assert extractor.discover_schema().tables[0].columns[0].name == "id"
    assert list(extractor.extract("default"))[0]["name"] == "A"


def test_mongodb_extractor_infers_sample():
    class Cursor:
        def __init__(self, docs):
            self.docs = docs
            self.skipped = 0

        def limit(self, _count):
            return iter(self.docs)

        def skip(self, count):
            self.skipped = count
            return self

        def batch_size(self, _size):
            return self

        def __iter__(self):
            return iter(self.docs[self.skipped :])

    class Database:
        def list_collection_names(self):
            return ["items"]

        def __getitem__(self, _name):
            return SimpleNamespace(
                find=lambda: Cursor(
                    [
                        {"_id": "abc", "name": "Ana", "n": None},
                        {"_id": "def", "name": "Beto", "extra": 1},
                    ]
                )
            )

    extractor = MongoDBExtractor({"uri": "mongodb://localhost", "database": "db"})
    extractor.db = Database()
    schema = extractor.discover_schema()
    assert schema.tables[0].name == "items"
    names = {column.name for column in schema.tables[0].columns}
    assert {"_id", "name", "extra"} <= names
    rows = list(extractor.extract("items", checkpoint={"skip": 1}))
    assert rows[0]["_id"] == "def"


def test_mysql_quote_style():
    from app.adapters.extractors.mysql_extractor import MySQLExtractor
    from app.services.identifiers import qualified_name

    assert MySQLExtractor.quote_style == "mysql"
    assert qualified_name("shop", "orders", "mysql") == "`shop`.`orders`"


def test_checkpoint_resume(client, admin_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "BATCH_SIZE", 2)

    class BoomExtractor(BaseExtractor):
        boom = True

        def connect(self):
            return None

        def close(self):
            return None

        def discover_schema(self):
            return SourceSchema(
                tables=[TableInfo(name="default", columns=[ColumnInfo(name="id", type="string")])]
            )

        def extract(self, table, batch_size=500, checkpoint=None):
            del table, batch_size
            skip = int((checkpoint or {}).get("skip") or 0)
            for index in range(skip, 5):
                if index == 3 and BoomExtractor.boom:
                    BoomExtractor.boom = False
                    raise RuntimeError("boom")
                yield {"id": str(index)}

    BoomExtractor.boom = True
    register_extractor("boom", BoomExtractor)
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"name": "boom_src", "type": "boom", "config": {}, "dedup_key": ["id"]},
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    failed = client.post(f"/api/v1/extract/{source_id}", headers=admin_headers)
    failed_job = client.get(f"/api/v1/jobs/{failed.json()['id']}", headers=admin_headers).json()
    assert failed_job["status"] == "failed"
    assert failed_job["checkpoint"]["skip"] == 2
    assert client.get("/api/v1/data/boom_src/default", headers=admin_headers).json()["total"] == 2

    retried = client.post(f"/api/v1/jobs/{failed_job['id']}/retry", headers=admin_headers)
    assert retried.status_code == 202
    final = client.get(f"/api/v1/jobs/{retried.json()['id']}", headers=admin_headers).json()
    assert final["status"] == "success"
    assert client.get("/api/v1/data/boom_src/default", headers=admin_headers).json()["total"] == 5
    assert get_extractor("boom", {}) is not None
