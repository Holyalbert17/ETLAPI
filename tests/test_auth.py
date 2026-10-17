def test_register_forces_user_role_and_login(client):
    created = client.post(
        "/api/v1/auth/register",
        json={
            "username": "nuevo",
            "email": "nuevo@example.com",
            "password": "secret123",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "user"

    token = client.post(
        "/api/v1/auth/login",
        data={"username": "nuevo", "password": "secret123"},
    )
    assert token.status_code == 200
    assert token.json()["token_type"] == "bearer"

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "nuevo"


def test_login_bad_password(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert response.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_duplicate_username(client):
    payload = {"username": "admin", "email": "other@example.com", "password": "secret123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
