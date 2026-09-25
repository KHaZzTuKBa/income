from datetime import datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app import db as db_module
from app.models import BrokerConnection, Instrument, Operation
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.invest_types import (
    AccountDTO,
    InstrumentDTO,
    InvestClientError,
    InvestPayload,
    OperationDTO,
    PositionDTO,
)
from app.services.sync import _upsert_instruments, begin_manual_sync, run_sync_job


def _payload() -> InvestPayload:
    occurred = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
    return InvestPayload(
        accounts=[
            AccountDTO("acc-broker", "Брокерский", "broker", "open", "READ_ONLY"),
            AccountDTO("acc-iis", "ИИС", "iis", "open", "READ_ONLY"),
        ],
        operations=[
            OperationDTO(
                broker_account_id="acc-broker",
                broker_operation_id="op-1",
                parent_operation_id="",
                figi="BBG004730N88",
                instrument_uid="uid-sber",
                operation_type="OPERATION_TYPE_BUY",
                name="Покупка SBER",
                state="OPERATION_STATE_EXECUTED",
                quantity=Decimal("10"),
                price=Decimal("250"),
                payment=Decimal("-2500"),
                commission=Decimal("-5"),
                currency="RUB",
                occurred_at=occurred,
            )
        ],
        positions=[
            PositionDTO(
                broker_account_id="acc-broker",
                figi="BBG004730N88",
                instrument_uid="uid-sber",
                instrument_type="share",
                quantity=Decimal("10"),
                average_price=Decimal("250"),
                average_price_currency="RUB",
                current_price=Decimal("270"),
                current_price_currency="RUB",
            ),
            PositionDTO(
                broker_account_id="acc-broker",
                figi="RUB000UTSTOM",
                instrument_uid="",
                instrument_type="currency",
                quantity=Decimal("1500"),
                average_price=Decimal("1"),
                average_price_currency="RUB",
                current_price=Decimal("1"),
                current_price_currency="RUB",
            ),
        ],
        instruments=[
            InstrumentDTO(
                figi="BBG004730N88",
                ticker="SBER",
                isin="RU0009029540",
                name="Сбербанк",
                instrument_type="share",
                currency="RUB",
                lot=1,
                uid="uid-sber",
            ),
            InstrumentDTO(figi="RUB000UTSTOM", ticker="RUB", name="Рубль", instrument_type="currency"),
        ],
    )


async def test_encrypt_roundtrip() -> None:
    token = "t." + "secret-token-value"
    assert decrypt_secret(encrypt_secret(token)) == token


async def test_connection_empty(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/settings/connection")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert "token" not in body or body.get("token") is None


async def test_save_token_encrypted_and_hidden(auth_client: AsyncClient, monkeypatch) -> None:
    async def fake_ping(token: str) -> None:
        assert token.startswith("t.")

    monkeypatch.setattr("app.api.routes.settings.ping_token", fake_ping)
    raw = "t." + ("a" * 40)
    response = await auth_client.put("/api/settings/connection", json={"token": raw})
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["token_hint"] == "••••aaaa"
    assert raw not in response.text
    assert "token_encrypted" not in body

    async with db_module.SessionLocal() as session:
        connection = (await session.execute(select(BrokerConnection))).scalar_one()
        assert connection.token_encrypted != raw
        assert decrypt_secret(connection.token_encrypted) == raw


async def test_save_token_rejected(auth_client: AsyncClient, monkeypatch) -> None:
    async def fake_ping(_token: str) -> None:
        raise InvestClientError("Invest API не принял токен. Нужен действующий read-only токен.")

    monkeypatch.setattr("app.api.routes.settings.ping_token", fake_ping)
    response = await auth_client.put("/api/settings/connection", json={"token": "t." + ("b" * 40)})
    assert response.status_code == 400
    empty = await auth_client.get("/api/settings/connection")
    assert empty.json()["configured"] is False


async def test_sync_without_token(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/sync")
    assert response.status_code == 400


async def test_sync_persists_and_is_idempotent(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()

    async def fake_ping(_token: str) -> None:
        return None

    async def fake_load(_token: str, accounts_only: bool = False) -> InvestPayload:
        return payload

    monkeypatch.setattr("app.api.routes.settings.ping_token", fake_ping)
    monkeypatch.setattr("app.services.sync.load_invest_data", fake_load)

    saved = await auth_client.put("/api/settings/connection", json={"token": "t." + ("c" * 40)})
    assert saved.status_code == 200

    async with db_module.SessionLocal() as session:
        run = await begin_manual_sync(session, user_id=1)
        run_id, connection_id = run.id, run.connection_id
    await run_sync_job(connection_id, run_id)

    accounts = await auth_client.get("/api/accounts")
    assert accounts.status_code == 200
    assert {item["type"] for item in accounts.json()} == {"broker", "iis"}

    positions = await auth_client.get("/api/positions")
    tickers = {item["ticker"] for item in positions.json()}
    assert "SBER" in tickers

    operations = await auth_client.get("/api/operations")
    assert len(operations.json()) == 1
    assert operations.json()[0]["broker_operation_id"] == "op-1"

    connection = await auth_client.get("/api/settings/connection")
    assert connection.json()["status"] == "ok"
    assert connection.json()["history_from"] == "2024-03-01"
    assert connection.json()["operations_count"] == 1

    async with db_module.SessionLocal() as session:
        run = await begin_manual_sync(session, user_id=1)
        await run_sync_job(run.connection_id, run.id)
        count = len((await session.execute(select(Operation))).scalars().all())
        assert count == 1

    runs = await auth_client.get("/api/sync/runs")
    assert runs.status_code == 200
    assert len(runs.json()) >= 2


async def test_sync_conflict(auth_client: AsyncClient, monkeypatch) -> None:
    async def fake_ping(_token: str) -> None:
        return None

    monkeypatch.setattr("app.api.routes.settings.ping_token", fake_ping)
    await auth_client.put("/api/settings/connection", json={"token": "t." + ("d" * 40)})

    async with db_module.SessionLocal() as session:
        connection = (await session.execute(select(BrokerConnection))).scalar_one()
        connection.status = "running"
        await session.commit()

    response = await auth_client.post("/api/sync")
    assert response.status_code == 409


async def test_upsert_stub_does_not_wipe_instrument(auth_client: AsyncClient, monkeypatch) -> None:
    from tests.test_dashboard import _seed

    payload = _payload()
    for item in payload.instruments:
        if item.figi == "BBG004730N88":
            item.sector = "financial"
    await _seed(auth_client, monkeypatch, payload, prices={})

    stub = InvestPayload(
        instruments=[InstrumentDTO(figi="BBG004730N88", name="BBG004730N88")],
    )
    async with db_module.SessionLocal() as session:
        await _upsert_instruments(session, stub)
        await session.commit()
        instrument = (
            await session.execute(select(Instrument).where(Instrument.figi == "BBG004730N88"))
        ).scalar_one()
        assert instrument.ticker == "SBER"
        assert instrument.name == "Сбербанк"
        assert instrument.instrument_type == "share"
        assert instrument.sector == "financial"
