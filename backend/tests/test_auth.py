from httpx import AsyncClient


async def test_login_success_and_me(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "test-password"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert "portfel_session" in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


async def test_login_wrong_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert response.status_code == 401
    me = await client.get("/api/auth/me")
    assert me.status_code == 401


async def test_me_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_logout(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "test-password"},
    )
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    me = await client.get("/api/auth/me")
    assert me.status_code == 401
