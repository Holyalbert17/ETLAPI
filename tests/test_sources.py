def test_create_source_requires_admin(client, user_headers):
    response = client.post(
        "/api/v1/sources",
        headers=user_headers,
        json={"name": "bloqueado", "type": "csv", "config": {"path": "x.csv"}},
    )
    assert response.status_code == 403


def test_create_list_get_update_and_delete(client, admin_headers, db):
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={
            "name": "src_csv",
            "type": "csv",
            "config": {"path": "datos.csv", "dsn": "postgresql://user:secret@localhost/db"},
            "dedup_policy": "upsert",
            "schedule": "0 */6 * * *",
            "contains_pii": True,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["config"]["dsn"] == "***"
    assert body["config"]["path"] == "datos.csv"
    source_id = body["id"]

    from app.domain.models import DataSource

    stored = db.get(DataSource, source_id)
    assert stored.config["dsn"].startswith("enc:v1:")

    listed = client.get("/api/v1/sources", headers=admin_headers)
    assert any(item["name"] == "src_csv" for item in listed.json())

    fetched = client.get(f"/api/v1/sources/{source_id}", headers=admin_headers)
    assert fetched.status_code == 200

    updated = client.patch(
        f"/api/v1/sources/{source_id}",
        headers=admin_headers,
        json={"config": {"path": "otro.csv", "dsn": "***"}, "active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["active"] is False
    assert updated.json()["config"]["path"] == "otro.csv"
    db.refresh(stored)
    assert stored.config["dsn"].startswith("enc:v1:")

    removed = client.delete(f"/api/v1/sources/{source_id}", headers=admin_headers)
    assert removed.status_code == 204
    assert client.get(f"/api/v1/sources/{source_id}", headers=admin_headers).status_code == 404


def test_duplicate_source_name(client, admin_headers):
    payload = {"name": "dup", "type": "csv", "config": {"path": "a.csv"}}
    assert client.post("/api/v1/sources", headers=admin_headers, json=payload).status_code == 201
    again = client.post("/api/v1/sources", headers=admin_headers, json=payload)
    assert again.status_code == 409


def test_invalid_schedule_and_type(client, admin_headers):
    bad_schedule = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"name": "mal_cron", "type": "csv", "config": {"path": "a.csv"}, "schedule": "nope"},
    )
    assert bad_schedule.status_code == 400
    bad_type = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"name": "mal_tipo", "type": "oracle", "config": {}},
    )
    assert bad_type.status_code == 400


def test_list_types(client, admin_headers):
    response = client.get("/api/v1/sources/types", headers=admin_headers)
    assert response.status_code == 200
    assert "postgres" in response.json()["types"]
    assert "web" in response.json()["types"]
