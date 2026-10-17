def test_query_filters_order_and_unknown_table(client, admin_headers, db):
    from app.domain.models import DataSource, DynamicRecord

    source = DataSource(
        name="qtest",
        type="csv",
        config={"path": "x"},
        discovered_schema={
            "tables": [
                {
                    "name": "t",
                    "columns": [
                        {"name": "n", "type": "string"},
                        {"name": "cat", "type": "string"},
                    ],
                }
            ]
        },
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    for index in range(5):
        db.add(
            DynamicRecord(
                source_id=source.id,
                table_name="t",
                data={"n": str(index), "cat": "a" if index % 2 == 0 else "b"},
                content_hash=f"h{index}",
                natural_key=str(index),
            )
        )
    db.commit()

    response = client.post(
        "/api/v1/data/qtest/query",
        headers=admin_headers,
        json={
            "table": "t",
            "filters": [{"field": "cat", "op": "eq", "value": "a"}],
            "order_by": "-n",
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert rows
    assert all(row["cat"] == "a" for row in rows)
    assert [row["n"] for row in rows] == ["4", "2", "0"]

    missing = client.get("/api/v1/data/qtest/otra", headers=admin_headers)
    assert missing.status_code == 404

    tables = client.get("/api/v1/data/qtest/tables", headers=admin_headers)
    assert "t" in tables.json()["tables"]

    injected = client.post(
        "/api/v1/data/qtest/query",
        headers=admin_headers,
        json={"table": "t", "filters": [{"field": "cat;drop", "op": "eq", "value": "a"}]},
    )
    assert injected.status_code == 400


def test_user_cannot_extract(client, user_headers, admin_headers, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"name": "solo_admin", "type": "csv", "config": {"path": str(path)}},
    )
    source_id = created.json()["id"]
    denied = client.post(f"/api/v1/extract/{source_id}", headers=user_headers)
    assert denied.status_code == 403


def test_health_openapi_metrics_and_correlation(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["x-correlation-id"]

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/sources" in spec.json()["paths"]
    assert "/api/v1/data/{source_name}/{table}" in spec.json()["paths"]

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]
