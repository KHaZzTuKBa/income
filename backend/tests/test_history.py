from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from httpx import AsyncClient

from app.services.history import aggregate_points, compute_snapshots
from app.services.invest_types import CURRENCY_FIGI
from tests.test_dashboard import _input, _seed
from tests.test_sync import _payload


def test_compute_snapshots_input_buy_and_price() -> None:
    t0 = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
    operations = [
        SimpleNamespace(
            id=1,
            account_id=1,
            figi="",
            operation_type="OPERATION_TYPE_INPUT",
            quantity=Decimal("0"),
            price=Decimal("0"),
            payment=Decimal("10000"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0 - timedelta(days=1),
            state="OPERATION_STATE_EXECUTED",
        ),
        SimpleNamespace(
            id=2,
            account_id=1,
            figi="BBG004730N88",
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("10"),
            price=Decimal("250"),
            payment=Decimal("-2500"),
            commission=Decimal("-5"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
    ]
    closes = {
        "BBG004730N88": {
            date(2024, 2, 29): Decimal("250"),
            date(2024, 3, 1): Decimal("250"),
            date(2024, 3, 2): Decimal("270"),
        }
    }
    rows = compute_snapshots(operations, {}, closes, {}, date(2024, 2, 29), date(2024, 3, 2))
    by_day = {item["day"]: item for item in rows}
    assert by_day[date(2024, 2, 29)]["cash"] == Decimal("10000")
    assert by_day[date(2024, 2, 29)]["securities"] == Decimal("0")
    assert by_day[date(2024, 2, 29)]["invested"] == Decimal("10000")
    assert by_day[date(2024, 3, 1)]["cash"] == Decimal("7495")
    assert by_day[date(2024, 3, 1)]["securities"] == Decimal("2500")
    assert by_day[date(2024, 3, 2)]["securities"] == Decimal("2700")
    assert by_day[date(2024, 3, 2)]["value"] == Decimal("10195")


def test_usd_instrument_rub_trade_not_multiplied_by_fx() -> None:
    """Бумага с currency=USD, купленная в рублях, не должна умножаться на курс доллара."""
    t0 = datetime(2023, 12, 27, 10, 0, tzinfo=timezone.utc)
    operations = [
        SimpleNamespace(
            id=1,
            account_id=1,
            figi="",
            operation_type="OPERATION_TYPE_INPUT",
            quantity=Decimal("0"),
            price=Decimal("0"),
            payment=Decimal("10000"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0 - timedelta(days=1),
            state="OPERATION_STATE_EXECUTED",
        ),
        SimpleNamespace(
            id=2,
            account_id=1,
            figi="US87238U2033",
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("2"),
            price=Decimal("3116"),
            payment=Decimal("-6232"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
    ]
    instrument = SimpleNamespace(
        figi="US87238U2033",
        ticker="T",
        currency="USD",
        instrument_type="share",
        nominal=Decimal("0"),
        nominal_currency="",
    )
    closes = {CURRENCY_FIGI["USD"]: {date(2023, 12, 26): Decimal("90"), date(2023, 12, 27): Decimal("90")}}
    rows = compute_snapshots(
        operations,
        {"US87238U2033": instrument},
        closes,
        {},
        date(2023, 12, 26),
        date(2023, 12, 27),
    )
    by_day = {item["day"]: item for item in rows}
    assert by_day[date(2023, 12, 26)]["value"] == Decimal("10000")
    bought = by_day[date(2023, 12, 27)]
    assert bought["securities"] == Decimal("6232")
    assert bought["value"] == Decimal("10000")
    assert bought["value"] < Decimal("600000")


def test_rub_scale_close_for_usd_instrument_stays_rub() -> None:
    t0 = datetime(2023, 12, 27, 10, 0, tzinfo=timezone.utc)
    operations = [
        SimpleNamespace(
            id=1,
            account_id=1,
            figi="US87238U2033",
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("2"),
            price=Decimal("3116"),
            payment=Decimal("-6232"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
    ]
    instrument = SimpleNamespace(
        figi="US87238U2033",
        ticker="T",
        currency="USD",
        instrument_type="share",
        nominal=Decimal("0"),
        nominal_currency="",
    )
    closes = {
        "US87238U2033": {date(2023, 12, 27): Decimal("3200")},
        CURRENCY_FIGI["USD"]: {date(2023, 12, 27): Decimal("90")},
    }
    rows = compute_snapshots(
        operations,
        {"US87238U2033": instrument},
        closes,
        {},
        date(2023, 12, 27),
        date(2023, 12, 27),
        close_currency={"US87238U2033": "USD"},
    )
    assert rows[0]["securities"] == Decimal("6400")
    assert rows[0]["value"] < Decimal("100000")


def test_aggregate_month_uses_last_day_not_sum() -> None:
    points = [
        {
            "day": date(2024, 1, 1),
            "value": Decimal("20000"),
            "cash": Decimal("0"),
            "securities": Decimal("20000"),
            "invested": Decimal("10000"),
            "imoex": Decimal("1"),
        },
        {
            "day": date(2024, 1, 15),
            "value": Decimal("25000"),
            "cash": Decimal("0"),
            "securities": Decimal("25000"),
            "invested": Decimal("10000"),
            "imoex": Decimal("1"),
        },
        {
            "day": date(2024, 1, 31),
            "value": Decimal("80000"),
            "cash": Decimal("0"),
            "securities": Decimal("80000"),
            "invested": Decimal("10000"),
            "imoex": Decimal("1"),
        },
        {
            "day": date(2024, 2, 1),
            "value": Decimal("81000"),
            "cash": Decimal("0"),
            "securities": Decimal("81000"),
            "invested": Decimal("10000"),
            "imoex": Decimal("1"),
        },
    ]
    monthly = aggregate_points(points, "month")
    assert [item["day"] for item in monthly] == [date(2024, 1, 31), date(2024, 2, 1)]
    assert monthly[0]["value"] == Decimal("80000")
    assert monthly[0]["value"] != sum(item["value"] for item in points if item["day"].month == 1)


async def test_history_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/history")
    assert response.status_code == 401


async def test_history_empty(auth_client: AsyncClient) -> None:
    body = (await auth_client.get("/api/history")).json()
    assert body["points"] == []
    assert body["series"] == []
    assert body["building"] is False


async def test_history_rebuild_from_candles(auth_client: AsyncClient, monkeypatch) -> None:
    async def fake_candles(_token, figi, _start, _end):
        if figi == "BBG004730N88":
            return [
                (date(2024, 3, 1), Decimal("250")),
                (date(2024, 3, 2), Decimal("270")),
            ]
        return []

    async def fake_imoex(_start, _end):
        return {date(2024, 3, 1): Decimal("3300"), date(2024, 3, 2): Decimal("3310")}

    monkeypatch.setattr("app.services.history.fetch_daily_candles", fake_candles)
    monkeypatch.setattr("app.services.history.fetch_imoex", fake_imoex)
    monkeypatch.setattr("app.services.history.moscow_today", lambda: date(2024, 3, 2))
    monkeypatch.setattr("app.services.xirr.moscow_today", lambda: date(2024, 3, 2))

    payload = _payload()
    occurred = payload.operations[0].occurred_at
    payload.operations.append(_input(Decimal("10000"), occurred - timedelta(days=1)))
    await _seed(auth_client, monkeypatch, payload, prices={})

    body = (await auth_client.get("/api/history?period=week&refresh=true")).json()
    assert len(body["points"]) >= 2
    last = body["points"][-1]
    assert last["day"] == "2024-03-02"
    assert last["value"] == "4200.00"
    assert any(item["imoex"] is not None for item in body["points"])
    names = {item["account_name"] for item in body["series"]}
    assert "Все счета" in names
    assert "Брокерский" in names
    assert body["granularity"] == "day"

    monthly = (await auth_client.get("/api/history?period=all")).json()
    assert monthly["granularity"] == "month"
    march = next(item for item in monthly["points"] if item["day"].startswith("2024-03"))
    assert march["value"] == "4200.00"
    assert Decimal(march["value"]) < Decimal("10000") * 31
