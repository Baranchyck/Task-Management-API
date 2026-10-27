from httpx import AsyncClient


async def test_register_user_success(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "newuser@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "duplicate@example.com", "password": "password123"}
    resp1 = await client.post("/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already registered" in resp2.json()["detail"].lower()


async def test_register_validation_errors(client: AsyncClient):
    # Invalid email
    resp1 = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "password123"},
    )
    assert resp1.status_code == 422

    # Password too short (< 6)
    resp2 = await client.post(
        "/auth/register",
        json={"email": "valid@example.com", "password": "123"},
    )
    assert resp2.status_code == 422


async def test_login_flow(client: AsyncClient):
    # 1. Register user
    email = "login_test@example.com"
    password = "secure_password"
    reg_resp = await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_resp.status_code == 201

    # 2. Login successfully
    login_resp = await client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 3. Use token to fetch current user
    token = token_data["access_token"]
    me_resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


async def test_login_invalid_credentials(client: AsyncClient):
    email = "valid_user@example.com"
    await client.post(
        "/auth/register",
        json={"email": email, "password": "correct_password"},
    )

    # Wrong password
    resp1 = await client.post(
        "/auth/login",
        data={"username": email, "password": "wrong_password"},
    )
    assert resp1.status_code == 401

    # Unknown user
    resp2 = await client.post(
        "/auth/login",
        data={"username": "unknown@example.com", "password": "some_password"},
    )
    assert resp2.status_code == 401


async def test_get_me_unauthorized(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
