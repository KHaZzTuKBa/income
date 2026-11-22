from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select

from app import db as db_module
from app.main import app
from app.models import BrokerConnection, Category, HoldingCategory, User
from app.services.crypto import encrypt_secret
from app.services.sync import active_connections_query
from tests.conftest import INVESTOR_USERNAME, TEST_PASSWORD

ACTIONS = "/api/admin/users/actions"
GOOD = {
    "username": "Petrov",
    "email": "Petrov@Example.com",
    "phone": "8 (999) 123-45-67",
    "password": "secret123",
}


@asynccontextmanager
async def _client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _register(client: AsyncClient, **overrides) -> Response:
    return await client.post("/api/auth/register", json={**GOOD, **overrides})


async def _login(client: AsyncClient, username: str, password: str) -> Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


async def _user_id(username: str) -> int:
    async with db_module.SessionLocal() as session:
        return (await session.execute(select(User.id).where(User.username == username))).scalar_one()


async def _usernames(admin_client: AsyncClient, **params) -> set[str]:
    response = await admin_client.get("/api/admin/users", params=params)
    assert response.status_code == 200
    return {item["username"] for item in response.json()["items"]}


async def test_register_creates_pending_request(client: AsyncClient) -> None:
    response = await _register(client)
    assert response.status_code == 201
    assert response.json() == {"status": "pending"}

    async with db_module.SessionLocal() as session:
        user = (await session.execute(select(User).where(User.username == "petrov"))).scalar_one()
        assert user.email == "petrov@example.com"
        assert user.phone == "+79991234567"
        assert user.status == "pending"
        assert user.is_admin is False
        assert user.password_hash != GOOD["password"]

    login = await _login(client, "PETROV", GOOD["password"])
    assert login.status_code == 403
    assert "рассмотрении" in login.json()["detail"]
    assert "portfel_session" not in login.cookies


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("username", "ab"),
        ("username", "1abc"),
        ("username", "иван"),
        ("username", "a" * 33),
        ("email", "no-at-sign"),
        ("email", "a@b"),
        ("phone", "12345"),
        ("phone", "+1 555 123 4567"),
        ("password", "short1"),
        ("password", "onlyletters"),
        ("password", "12345678"),
    ],
)
async def test_register_validation(client: AsyncClient, field: str, value: str) -> None:
    response = await _register(client, **{field: value})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


async def test_register_password_equal_to_login(client: AsyncClient) -> None:
    response = await _register(client, username="user12345", password="User12345")
    assert response.status_code == 422


async def test_register_duplicates(client: AsyncClient) -> None:
    assert (await _register(client)).status_code == 201
    cases = [
        {"username": "PETROV", "email": "other@example.com", "phone": "+79990000002"},
        {"username": "other", "email": "PETROV@example.com", "phone": "+79990000002"},
        {"username": "other", "email": "other@example.com", "phone": "+7 999 123 45 67"},
        {"username": "ADMIN", "email": "x@example.com", "phone": "+79990000003"},
        {"username": INVESTOR_USERNAME, "email": "y@example.com", "phone": "+79990000004"},
    ]
    for case in cases:
        response = await _register(client, **case)
        assert response.status_code == 409, case


async def test_roles_are_separated(auth_client: AsyncClient, admin_client: AsyncClient) -> None:
    me = await admin_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["is_admin"] is True
    assert (await auth_client.get("/api/auth/me")).json()["is_admin"] is False

    assert (await admin_client.get("/api/dashboard")).status_code == 403
    assert (await admin_client.get("/api/categories")).status_code == 403
    assert (await admin_client.get("/api/settings/connection")).status_code == 403

    assert (await auth_client.get("/api/admin/users")).status_code == 403
    assert (await auth_client.post(ACTIONS, json={"ids": [1], "action": "freeze"})).status_code == 403
    assert (await auth_client.get("/api/admin/legacy-portfolio")).status_code == 403

    async with _client() as anon:
        assert (await anon.get("/api/admin/users")).status_code == 401
        assert (await anon.post(ACTIONS, json={"ids": [1], "action": "approve"})).status_code == 401


async def test_bulk_approve_and_reject(client: AsyncClient, admin_client: AsyncClient) -> None:
    await _register(client)
    await _register(client, username="sidorov", email="s@example.com", phone="+79990000005")
    petrov, sidorov = await _user_id("petrov"), await _user_id("sidorov")
    admin_id = (await admin_client.get("/api/auth/me")).json()["id"]

    listing = await admin_client.get("/api/admin/users", params={"status": "pending"})
    assert {item["username"] for item in listing.json()["items"]} == {"petrov", "sidorov"}
    assert listing.json()["counts"]["pending"] == 2
    assert listing.json()["counts"]["active"] == 1

    approve = await admin_client.post(ACTIONS, json={"ids": [petrov, admin_id], "action": "approve"})
    assert approve.json() == {"updated": 1, "skipped": 1}
    reject = await admin_client.post(ACTIONS, json={"ids": [sidorov, petrov], "action": "reject"})
    assert reject.json() == {"updated": 1, "skipped": 1}

    async with _client() as user:
        assert (await _login(user, "petrov", GOOD["password"])).status_code == 200
        assert (await user.get("/api/dashboard")).status_code == 200

    rejected = await _login(client, "sidorov", GOOD["password"])
    assert rejected.status_code == 403
    assert "отклонена" in rejected.json()["detail"]
    assert await _usernames(admin_client, status="rejected") == {"sidorov"}

    again = await admin_client.post(ACTIONS, json={"ids": [sidorov], "action": "approve"})
    assert again.json() == {"updated": 1, "skipped": 0}
    assert (await _login(client, "sidorov", GOOD["password"])).status_code == 200


async def test_freeze_drops_session_and_unfreeze(auth_client: AsyncClient, admin_client: AsyncClient) -> None:
    investor = await _user_id(INVESTOR_USERNAME)
    assert (await auth_client.get("/api/dashboard")).status_code == 200

    frozen = await admin_client.post(ACTIONS, json={"ids": [investor], "action": "freeze"})
    assert frozen.json() == {"updated": 1, "skipped": 0}
    assert (await auth_client.get("/api/dashboard")).status_code == 401
    me = await auth_client.get("/api/auth/me")
    assert me.status_code == 401
    assert me.json()["detail"] == "Аккаунт заморожен"

    login = await _login(auth_client, INVESTOR_USERNAME, TEST_PASSWORD)
    assert login.status_code == 403
    assert login.json()["detail"] == "Аккаунт заморожен"
    assert await _usernames(admin_client, status="frozen") == {INVESTOR_USERNAME}

    unfrozen = await admin_client.post(ACTIONS, json={"ids": [investor], "action": "unfreeze"})
    assert unfrozen.json() == {"updated": 1, "skipped": 0}
    assert (await _login(auth_client, INVESTOR_USERNAME, TEST_PASSWORD)).status_code == 200
    assert (await auth_client.get("/api/dashboard")).status_code == 200


async def test_admin_cannot_act_on_self(admin_client: AsyncClient) -> None:
    admin_id = (await admin_client.get("/api/auth/me")).json()["id"]
    for action in ("freeze", "reject", "delete"):
        response = await admin_client.post(ACTIONS, json={"ids": [admin_id], "action": action})
        assert response.json() == {"updated": 0, "skipped": 1}
    assert (await admin_client.get("/api/auth/me")).status_code == 200
    assert "admin" not in await _usernames(admin_client)


async def test_delete_user(auth_client: AsyncClient, admin_client: AsyncClient) -> None:
    investor = await _user_id(INVESTOR_USERNAME)
    deleted = await admin_client.post(ACTIONS, json={"ids": [investor], "action": "delete"})
    assert deleted.json() == {"updated": 1, "skipped": 0}

    assert (await auth_client.get("/api/dashboard")).status_code == 401
    assert (await _login(auth_client, INVESTOR_USERNAME, TEST_PASSWORD)).status_code == 401
    assert INVESTOR_USERNAME not in await _usernames(admin_client)


async def test_search_by_login_email_phone(client: AsyncClient, admin_client: AsyncClient) -> None:
    await _register(client)
    for query in ("PETR", "example.com", "123-45", "8 999 123", "+7999123"):
        assert "petrov" in await _usernames(admin_client, q=query), query
    assert await _usernames(admin_client, q="investor@") == {INVESTOR_USERNAME}
    assert await _usernames(admin_client, q="nobody") == set()
    assert await _usernames(admin_client, q="%") == set()


async def test_same_figi_in_categories_of_two_users(
    client: AsyncClient, auth_client: AsyncClient, admin_client: AsyncClient
) -> None:
    await _register(client)
    await admin_client.post(ACTIONS, json={"ids": [await _user_id("petrov")], "action": "approve"})

    async with _client() as other:
        assert (await _login(other, "petrov", GOOD["password"])).status_code == 200
        for user_client in (auth_client, other):
            created = await user_client.post("/api/categories", json={"name": "Акции"})
            assert created.status_code == 201
            assigned = await user_client.put(
                "/api/categories/assignments",
                json={"figi": "BBG004730N88", "category_id": created.json()["id"]},
            )
            assert assigned.status_code == 204

    async with db_module.SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(HoldingCategory).where(HoldingCategory.figi == "BBG004730N88")
        )
        assert count == 2


async def test_transfer_legacy_portfolio(client: AsyncClient, admin_client: AsyncClient) -> None:
    admin_id = (await admin_client.get("/api/auth/me")).json()["id"]
    empty = await admin_client.get("/api/admin/legacy-portfolio")
    assert empty.json()["has_portfolio"] is False

    async with db_module.SessionLocal() as session:
        session.add(
            BrokerConnection(
                user_id=admin_id,
                token_encrypted=encrypt_secret("t." + ("z" * 40)),
                token_hint="zzzz",
            )
        )
        category = Category(user_id=admin_id, name="Легаси")
        session.add(category)
        await session.flush()
        session.add(HoldingCategory(user_id=admin_id, category_id=category.id, figi="BBG004730N88"))
        await session.commit()

    legacy = await admin_client.get("/api/admin/legacy-portfolio")
    assert legacy.json()["has_portfolio"] is True
    assert legacy.json()["categories_count"] == 1
    assert legacy.json()["token_hint"] == "zzzz"

    await _register(client)
    petrov = await _user_id("petrov")
    pending = await admin_client.post("/api/admin/legacy-portfolio/transfer", json={"user_id": petrov})
    assert pending.status_code == 409

    await admin_client.post(ACTIONS, json={"ids": [petrov], "action": "approve"})
    moved = await admin_client.post("/api/admin/legacy-portfolio/transfer", json={"user_id": petrov})
    assert moved.status_code == 204
    assert (await admin_client.get("/api/admin/legacy-portfolio")).json()["has_portfolio"] is False

    again = await admin_client.post("/api/admin/legacy-portfolio/transfer", json={"user_id": petrov})
    assert again.status_code == 409

    async with _client() as user:
        assert (await _login(user, "petrov", GOOD["password"])).status_code == 200
        connection = await user.get("/api/settings/connection")
        assert connection.json()["configured"] is True
        assert connection.json()["token_hint"] == "••••zzzz"

    async with db_module.SessionLocal() as session:
        category = (await session.execute(select(Category))).scalar_one()
        holding = (await session.execute(select(HoldingCategory))).scalar_one()
        assert category.user_id == petrov
        assert holding.user_id == petrov


async def test_background_jobs_skip_frozen(auth_client: AsyncClient, admin_client: AsyncClient) -> None:
    investor = await _user_id(INVESTOR_USERNAME)
    async with db_module.SessionLocal() as session:
        session.add(BrokerConnection(user_id=investor, token_encrypted="", token_hint=""))
        await session.commit()
        assert len((await session.execute(active_connections_query())).scalars().all()) == 1

    await admin_client.post(ACTIONS, json={"ids": [investor], "action": "freeze"})
    async with db_module.SessionLocal() as session:
        assert (await session.execute(active_connections_query())).scalars().all() == []


async def test_change_password(auth_client: AsyncClient, admin_client: AsyncClient) -> None:
    wrong = await auth_client.post(
        "/api/auth/password", json={"current_password": "nope", "new_password": "newpass123"}
    )
    assert wrong.status_code == 400
    weak = await auth_client.post(
        "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "short"}
    )
    assert weak.status_code == 422
    ok = await auth_client.post(
        "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "newpass123"}
    )
    assert ok.status_code == 204

    await auth_client.post("/api/auth/logout")
    assert (await _login(auth_client, INVESTOR_USERNAME, TEST_PASSWORD)).status_code == 401
    assert (await _login(auth_client, INVESTOR_USERNAME, "newpass123")).status_code == 200

    admin = await admin_client.post(
        "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "newpass123"}
    )
    assert admin.status_code == 403
