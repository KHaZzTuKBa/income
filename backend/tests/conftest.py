import os

from cryptography.fernet import Fernet

os.environ["APP_USERNAME"] = "admin"
os.environ["APP_PASSWORD"] = "test-password"
os.environ["SESSION_SECRET"] = "test-session-secret-not-for-prod-32"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.db import Base
from app.main import app
from app.seed import seed_user


@pytest.fixture
async def client() -> AsyncClient:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    db_module.SessionLocal = factory

    async with factory() as session:
        await seed_user(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "test-password"},
    )
    assert response.status_code == 200
    return client
