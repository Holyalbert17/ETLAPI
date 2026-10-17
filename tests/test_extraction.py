import csv


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def test_csv_extraction_is_idempotent(client, admin_headers, tmp_path):
    path = tmp_path / "people.csv"
    _write_csv(path, [["id", "nombre", "alta"], ["1", "Ana", "2024-01-15"], ["2", "Beto", "15/02/2024"]])
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={
            "name": "csv_people",
            "type": "csv",
            "config": {"path": str(path)},
            "dedup_key": ["id"],
            "dedup_policy": "upsert",
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]

    schema = client.get(f"/api/v1/sources/{source_id}/schema", headers=admin_headers)
    assert schema.status_code == 200, schema.text
    assert schema.json()["tables"][0]["name"] == "default"
    assert schema.json()["diff"]["changed"] is True

    again = client.get(f"/api/v1/sources/{source_id}/schema", headers=admin_headers)
    assert again.json()["diff"]["changed"] is False

    first = client.post(f"/api/v1/extract/{source_id}", headers=admin_headers)
    assert first.status_code == 202
    job_id = first.json()["id"]
    job = client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)
    assert job.status_code == 200
    assert job.json()["status"] == "success"
    assert job.json()["rows_extracted"] == 2

    data = client.get("/api/v1/data/csv_people/default", headers=admin_headers)
    assert data.status_code == 200
    assert data.json()["total"] == 2
    assert data.json()["data"][0]["alta"] == "2024-01-15"

    second = client.post(f"/api/v1/extract/{source_id}", headers=admin_headers)
    assert second.status_code == 202
    second_job = client.get(f"/api/v1/jobs/{second.json()['id']}", headers=admin_headers).json()
    assert second_job["rows_updated"] == 2
    assert client.get("/api/v1/data/csv_people/default", headers=admin_headers).json()["total"] == 2


def test_mapping_validation_and_errors(client, admin_headers, tmp_path):
    path = tmp_path / "mails.csv"
    _write_csv(path, [["id", "correo"], ["1", "ana@example.com"], ["2", "no-es-email"]])
    created = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={
            "name": "csv_mails",
            "type": "csv",
            "config": {
                "path": str(path),
                "required_fields": ["email"],
                "constraints": {"email": {"format": "email"}},
            },
            "canonical_mapping": {"default": {"correo": "email"}},
            "dedup_key": ["id"],
            "contains_pii": True,
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    started = client.post(f"/api/v1/extract/{source_id}", headers=admin_headers)
    job = client.get(f"/api/v1/jobs/{started.json()['id']}", headers=admin_headers).json()
    assert job["status"] == "partial"
    assert job["rows_inserted"] == 1
    assert job["errors_count"] >= 1

    data = client.get("/api/v1/data/csv_mails/default?filter=email:ana@example.com", headers=admin_headers)
    assert data.status_code == 200
    assert data.json()["total"] == 1
    assert data.json()["data"][0]["email"] == "ana@example.com"
    assert "correo" not in data.json()["data"][0]

    blocked = client.get("/api/v1/data/csv_mails/default?order_by=correo;drop", headers=admin_headers)
    assert blocked.status_code == 400

    projected = client.post(
        "/api/v1/data/csv_mails/query",
        headers=admin_headers,
        json={"table": "default", "columns": ["email"], "limit": 10},
    )
    assert projected.status_code == 200
    assert set(projected.json()["data"][0]) == {"email"}

    errors = client.get(f"/api/v1/errors?job_id={job['id']}&stage=validation", headers=admin_headers)
    assert errors.status_code == 200
    assert errors.json()[0]["stage"] == "validation"
    assert errors.json()[0]["stack_trace"]

    audit = client.get("/api/v1/audit", headers=admin_headers)
    assert audit.status_code == 200
    assert any(item["action"] == "data_read" for item in audit.json())
