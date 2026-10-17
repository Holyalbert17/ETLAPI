import os
from pathlib import Path

_DB = Path(__file__).resolve().parent / "_test.db"
if _DB.exists():
    try:
        _DB.unlink()
    except OSError:
        pass

os.environ["DATABASE_URL"] = "sqlite:///" + _DB.as_posix()
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key"
os.environ["ADMIN_USERNAME"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["RETRY_BACKOFF"] = "0"
os.environ["MAX_RETRIES"] = "2"
os.environ["REDIS_URL"] = ""
os.environ["ERROR_WEBHOOK_URL"] = ""
os.environ["LOG_LEVEL"] = "WARNING"

import pytest
from app.database import Base, SessionLocal, engine, get_db
from app.domain.models import User
from app.main import app
from app.security import hash_password
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(
        User(
            username="admin",
            email="admin@example.com",
            hashed_password=hash_password("admin123"),
            role="admin",
        )
    )
    db.add(
        User(
            username="user",
            email="user@example.com",
            hashed_password=hash_password("user123"),
            role="user",
        )
    )
    db.commit()
    db.close()
    yield
    engine.dispose()
    try:
        _DB.unlink()
    except OSError:
        pass


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def user_token(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "user", "password": "user123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}
