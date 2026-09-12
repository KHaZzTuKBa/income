from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from httpx import AsyncClient

from app import db as db_module
from app.services.invest_types import InstrumentDTO, OperationDTO, PositionDTO
from app.services.portfolio import quoted_unit_price, remaining_lots
from app.services.sync import begin_manual_sync, run_sync_job
from tests.test_sync import _payload


def _buy(
    *,
    op_id: str,
    qty: Decimal,
    price: Decimal,
    when: datetime,
    figi: str = "BBG004730N88",
) -> OperationDTO:
    return OperationDTO(
        broker_account_id="acc-broker",
        broker_operation_id=op_id,
        parent_operation_id="",
        figi=figi,
        instrument_uid="uid-sber",
        operation_type="OPERATION_TYPE_BUY",
        name="Покупка",
        state="OPERATION_STATE_EXECUTED",
        quantity=qty,
        price=price,
        payment=-(qty * price),
        commission=Decimal("0"),
        currency="RUB",
        occurred_at=when,
    )


def _input(amount: Decimal, when: datetime, op_id: str = "op-in") -> OperationDTO:
    return OperationDTO(
        broker_account_id="acc-broker",
        broker_operation_id=op_id,
        parent_operation_id="",
        figi="",
        instrument_uid="",
        operation_type="OPERATION_TYPE_INPUT",
        name="Пополнение",
        state="OPERATION_STATE_EXECUTED",
        quantity=Decimal("0"),
        price=Decimal("0"),
        payment=amount,
        commission=Decimal("0"),
        currency="RUB",
        occurred_at=when,
    )


def _output(amount: Decimal, when: datetime) -> OperationDTO:
    return OperationDTO(
        broker_account_id="acc-broker",
        broker_operation_id="op-out",
        parent_operation_id="",
        figi="",
        instrument_uid="",
        operation_type="OPERATION_TYPE_OUTPUT",
        name="Вывод",
        state="OPERATION_STATE_EXECUTED",
        quantity=Decimal("0"),
        price=Decimal("0"),
        payment=-abs(amount),
        commission=Decimal("0"),
        currency="RUB",
        occurred_at=when,
    )


async def _seed(auth_client: AsyncClient, monkeypatch, payload, prices: dict[str, Decimal] | None) -> None:
    async def fake_ping(_token: str) -> None:
        return None

    async def fake_load(_token: str, accounts_only: bool = False):
        return payload

    async def fake_prices(_token: str, _figis) -> dict[str, Decimal]:
        return dict(prices or {})

    monkeypatch.setattr("app.api.routes.settings.ping_token", fake_ping)
    monkeypatch.setattr("app.services.sync.load_invest_data", fake_load)
    monkeypatch.setattr("app.services.portfolio.fetch_last_prices", fake_prices)

    async def fake_nominals(_token: str, _figis) -> dict:
        return {}

    monkeypatch.setattr("app.services.invest.fetch_instrument_nominals", fake_nominals)

    saved = await auth_client.put("/api/settings/connection", json={"token": "t." + ("e" * 40)})
    assert saved.status_code == 200

    async with db_module.SessionLocal() as session:
        run = await begin_manual_sync(session, user_id=1)
        run_id, connection_id = run.id, run.connection_id
    await run_sync_job(connection_id, run_id)


def test_remaining_lots_average_after_sell() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ops = [
        SimpleNamespace(
            id=1,
            account_id=1,
            figi="F",
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("10"),
            price=Decimal("250"),
            payment=Decimal("-2500"),
            occurred_at=t0,
        ),
        SimpleNamespace(
            id=2,
            account_id=1,
            figi="F",
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("10"),
            price=Decimal("350"),
            payment=Decimal("-3500"),
            occurred_at=t0 + timedelta(days=1),
        ),
        SimpleNamespace(
            id=3,
            account_id=1,
            figi="F",
            operation_type="OPERATION_TYPE_SELL",
            quantity=Decimal("5"),
            price=Decimal("400"),
            payment=Decimal("2000"),
            occurred_at=t0 + timedelta(days=2),
        ),
    ]
    qty, avg = remaining_lots(ops)[(1, "F")]
    assert qty == Decimal("15")
    assert avg == Decimal("300")


async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/dashboard")
    assert response.status_code == 401


async def test_dashboard_empty(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == "0.00"
    assert body["invested"] == "0.00"
    assert body["profit"] == "0.00"
    assert body["positions"] == []
    assert body["invested_missing"] is False


async def test_dashboard_value_invested_profit(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    occurred = payload.operations[0].occurred_at
    payload.operations.append(_input(Decimal("10000"), occurred - timedelta(days=1)))

    await _seed(auth_client, monkeypatch, payload, prices={})

    response = await auth_client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == "4200.00"
    assert body["invested"] == "10000.00"
    assert body["profit"] == "-5800.00"
    assert body["profit_percent"] == "-58.00"
    assert body["cash"] == "1500.00"
    assert body["prices_live"] is False
    assert body["invested_missing"] is False

    by_ticker = {item["ticker"]: item for item in body["positions"]}
    sber = by_ticker["SBER"]
    assert sber["quantity"] == "10"
    assert sber["average_price"] == "250"
    assert sber["average_source"] == "operations"
    assert sber["current_price"] == "270"
    assert sber["value"] == "2700.00"
    assert sber["cost"] == "2500.00"
    assert sber["pnl"] == "200.00"
    assert sber["is_cash"] is False
    assert sber["share"] == "64.29"

    cash = by_ticker["RUB"]
    assert cash["is_cash"] is True
    assert cash["value"] == "1500.00"
    assert cash["pnl"] == "0.00"
    assert cash["share"] == "35.71"


async def test_dashboard_live_price_and_output(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    occurred = payload.operations[0].occurred_at
    payload.operations.append(_input(Decimal("10000"), occurred - timedelta(days=2)))
    payload.operations.append(_output(Decimal("2000"), occurred - timedelta(days=1)))

    await _seed(
        auth_client,
        monkeypatch,
        payload,
        prices={"BBG004730N88": Decimal("280")},
    )

    body = (await auth_client.get("/api/dashboard")).json()
    assert body["prices_live"] is True
    assert body["invested"] == "8000.00"
    assert body["value"] == "4300.00"
    assert body["profit"] == "-3700.00"
    sber = next(item for item in body["positions"] if item["ticker"] == "SBER")
    assert sber["current_price"] == "280"
    assert sber["value"] == "2800.00"
    assert sber["pnl"] == "300.00"


async def test_dashboard_average_from_two_buys(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    t0 = payload.operations[0].occurred_at
    payload.operations = [
        _input(Decimal("10000"), t0 - timedelta(days=2)),
        _buy(op_id="op-1", qty=Decimal("10"), price=Decimal("250"), when=t0),
        _buy(op_id="op-2", qty=Decimal("10"), price=Decimal("350"), when=t0 + timedelta(hours=1)),
    ]
    payload.positions = [
        PositionDTO(
            broker_account_id="acc-broker",
            figi="BBG004730N88",
            instrument_uid="uid-sber",
            instrument_type="share",
            quantity=Decimal("20"),
            average_price=Decimal("999"),
            average_price_currency="RUB",
            current_price=Decimal("400"),
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
    ]

    await _seed(auth_client, monkeypatch, payload, prices={})
    body = (await auth_client.get("/api/dashboard")).json()
    sber = next(item for item in body["positions"] if item["ticker"] == "SBER")
    assert sber["average_price"] == "300"
    assert sber["average_source"] == "operations"
    assert sber["cost"] == "6000.00"
    assert sber["value"] == "8000.00"
    assert body["value"] == "9500.00"


async def test_dashboard_usd_cash_fx(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.positions.append(
        PositionDTO(
            broker_account_id="acc-broker",
            figi="BBG0013HGFT4",
            instrument_uid="",
            instrument_type="currency",
            quantity=Decimal("100"),
            average_price=Decimal("1"),
            average_price_currency="USD",
            current_price=Decimal("1"),
            current_price_currency="USD",
        )
    )
    payload.instruments.append(
        InstrumentDTO(
            figi="BBG0013HGFT4",
            ticker="USD",
            name="Доллар США",
            instrument_type="currency",
            currency="USD",
        )
    )

    await _seed(
        auth_client,
        monkeypatch,
        payload,
        prices={"BBG0013HGFT4": Decimal("90")},
    )
    body = (await auth_client.get("/api/dashboard")).json()
    assert body["value"] == "13200.00"
    assert body["cash"] == "10500.00"
    usd = next(item for item in body["positions"] if item["ticker"] == "USD")
    assert usd["is_cash"] is True
    assert usd["value"] == "9000.00"


async def test_dashboard_invested_missing_without_deposits(
    auth_client: AsyncClient, monkeypatch
) -> None:
    await _seed(auth_client, monkeypatch, _payload(), prices={})
    body = (await auth_client.get("/api/dashboard")).json()
    assert body["invested"] == "0.00"
    assert body["value"] == "4200.00"
    assert body["profit"] == "4200.00"
    assert body["invested_missing"] is True
    assert body["profit_percent"] is None


def test_bond_percent_quote_uses_nominal() -> None:
    assert quoted_unit_price(
        Decimal("95.5"),
        instrument_type="bond",
        nominal=Decimal("1000"),
        average=Decimal("980"),
    ) == Decimal("955")


async def test_dashboard_bond_percent_of_par(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.positions.append(
        PositionDTO(
            broker_account_id="acc-broker",
            figi="BOND1",
            instrument_uid="",
            instrument_type="bond",
            quantity=Decimal("10"),
            average_price=Decimal("980"),
            average_price_currency="RUB",
            current_price=Decimal("95.5"),
            current_price_currency="RUB",
        )
    )
    payload.instruments.append(
        InstrumentDTO(
            figi="BOND1",
            ticker="BOND",
            name="Облигация",
            instrument_type="bond",
            currency="RUB",
            nominal=Decimal("1000"),
            nominal_currency="RUB",
        )
    )
    await _seed(auth_client, monkeypatch, payload, prices={"BOND1": Decimal("95.5")})
    body = (await auth_client.get("/api/dashboard")).json()
    bond = next(item for item in body["positions"] if item["ticker"] == "BOND")
    assert bond["current_price"] == "955"
    assert bond["value"] == "9550.00"
    assert bond["cost"] == "9800.00"
    assert bond["pnl"] == "-250.00"


async def test_dashboard_dedupes_usd_cash(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.positions.extend(
        [
            PositionDTO(
                broker_account_id="acc-broker",
                figi="USD800UTSTOM",
                instrument_uid="",
                instrument_type="currency",
                quantity=Decimal("100"),
                average_price=Decimal("1"),
                average_price_currency="RUB",
                current_price=Decimal("1"),
                current_price_currency="RUB",
            ),
            PositionDTO(
                broker_account_id="acc-broker",
                figi="BBG0013HGFT4",
                instrument_uid="",
                instrument_type="currency",
                quantity=Decimal("100"),
                average_price=Decimal("1"),
                average_price_currency="USD",
                current_price=Decimal("1"),
                current_price_currency="USD",
            ),
        ]
    )
    payload.instruments.extend(
        [
            InstrumentDTO(
                figi="USD800UTSTOM",
                ticker="USD000UTSTOM",
                name="Доллар США",
                instrument_type="currency",
            ),
            InstrumentDTO(
                figi="BBG0013HGFT4",
                ticker="USD000UTSTOM",
                name="Доллар США",
                instrument_type="currency",
                currency="USD",
            ),
        ]
    )
    await _seed(
        auth_client,
        monkeypatch,
        payload,
        prices={"BBG0013HGFT4": Decimal("90")},
    )
    body = (await auth_client.get("/api/dashboard")).json()
    usd_rows = [item for item in body["positions"] if item["is_cash"] and item["ticker"] == "USD"]
    assert len(usd_rows) == 1
    assert usd_rows[0]["value"] == "9000.00"
    assert body["cash"] == "10500.00"


async def test_dashboard_usd_bond_inferred_nominal(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.positions.append(
        PositionDTO(
            broker_account_id="acc-broker",
            figi="USDBOND",
            instrument_uid="",
            instrument_type="bond",
            quantity=Decimal("1"),
            average_price=Decimal("8670"),
            average_price_currency="RUB",
            current_price=Decimal("100.45"),
            current_price_currency="RUB",
        )
    )
    payload.instruments.append(
        InstrumentDTO(
            figi="USDBOND",
            ticker="SIBUR",
            name="СИБУР USD",
            instrument_type="bond",
            currency="USD",
        )
    )
    await _seed(
        auth_client,
        monkeypatch,
        payload,
        prices={"BBG0013HGFT4": Decimal("90"), "USDBOND": Decimal("100.45")},
    )
    body = (await auth_client.get("/api/dashboard")).json()
    bond = next(item for item in body["positions"] if item["ticker"] == "SIBUR")
    assert bond["current_price"] == "100.45"
    assert bond["current_price_currency"] == "USD"
    assert bond["value"] == "9040.50"
    assert bond["cost"] == "8670.00"
