from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from httpx import AsyncClient

from app.services.history import (
    aggregate_points,
    canonical_figi_map,
    compute_snapshots,
    opening_balances,
    period_invested_and_profit,
)
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
    total = next(item for item in monthly["series"] if item["account_id"] is None)
    assert total["open_value"] == "0.00"
    assert total["open_invested"] == "0.00"
    invested_delta, profit = period_invested_and_profit(
        Decimal(total["open_value"]),
        Decimal(total["open_invested"]),
        Decimal(march["value"]),
        Decimal(march["invested"]),
    )
    assert invested_delta == Decimal(march["invested"])
    assert profit == Decimal(march["value"]) - Decimal(march["invested"])

    custom = (await auth_client.get("/api/history?period=custom&from=2024-03-02&to=2024-03-02")).json()
    mar1 = next(item for item in body["points"] if item["day"] == "2024-03-01")
    custom_total = next(item for item in custom["series"] if item["account_id"] is None)
    assert custom_total["open_value"] == mar1["value"]
    assert custom_total["open_invested"] == mar1["invested"]


def test_opening_balances_uses_day_before_window() -> None:
    rows = [
        SimpleNamespace(day=date(2024, 1, 31), value_rub=Decimal("80000"), invested_rub=Decimal("50000")),
        SimpleNamespace(day=date(2024, 2, 29), value_rub=Decimal("90000"), invested_rub=Decimal("70000")),
        SimpleNamespace(day=date(2024, 3, 31), value_rub=Decimal("95000"), invested_rub=Decimal("70000")),
    ]
    assert opening_balances(rows, date(2024, 1, 1)) == (Decimal("0"), Decimal("0"))
    assert opening_balances(rows, date(2024, 3, 1)) == (Decimal("90000"), Decimal("70000"))
    invested_delta, profit = period_invested_and_profit(
        Decimal("90000"),
        Decimal("70000"),
        Decimal("95000"),
        Decimal("70000"),
    )
    assert invested_delta == Decimal("0")
    assert profit == Decimal("5000")
    deposited, profit_with_cash = period_invested_and_profit(
        Decimal("90000"),
        Decimal("70000"),
        Decimal("110000"),
        Decimal("85000"),
    )
    assert deposited == Decimal("15000")
    assert profit_with_cash == Decimal("5000")


def _etf(figi: str, ticker: str, isin: str = "RU000A106DL2") -> SimpleNamespace:
    return SimpleNamespace(
        figi=figi,
        ticker=ticker,
        isin=isin,
        currency="RUB",
        instrument_type="etf",
        nominal=Decimal("0"),
        nominal_currency="",
    )


def test_replaced_figi_uses_current_figi_candles() -> None:
    """Журнал со старым FIGI TMON, свечи и позиция с новым — цена не должна падать на среднюю."""
    old = "TCS10A106DL2"
    new = "TCSM99706DL2"
    t0 = datetime(2024, 4, 11, 12, 0, tzinfo=timezone.utc)
    operations = [
        SimpleNamespace(
            id=1,
            account_id=2,
            figi="",
            operation_type="OPERATION_TYPE_INPUT",
            quantity=Decimal("0"),
            price=Decimal("0"),
            payment=Decimal("1600"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
        SimpleNamespace(
            id=2,
            account_id=2,
            figi=old,
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            payment=Decimal("-1000"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
    ]
    instruments = {old: _etf(old, "TMON"), new: _etf(new, "TMON")}
    aliases = canonical_figi_map(instruments, preferred={new})
    assert aliases[old] == new
    closes = {new: {date(2024, 4, 11): Decimal("160"), date(2024, 4, 12): Decimal("164")}}
    rows = compute_snapshots(
        operations,
        instruments,
        closes,
        {},
        date(2024, 4, 11),
        date(2024, 4, 12),
        figi_aliases=aliases,
    )
    by_day = {item["day"]: item for item in rows}
    assert by_day[date(2024, 4, 11)]["securities"] == Decimal("1600")
    assert by_day[date(2024, 4, 12)]["securities"] == Decimal("1640")
    assert by_day[date(2024, 4, 12)]["value"] != Decimal("1000")


def test_weekend_ticker_not_merged_with_main() -> None:
    mapping = canonical_figi_map(
        {
            "TCS10A106DL2": _etf("TCS10A106DL2", "TMON"),
            "TCSM99706DL2": _etf("TCSM99706DL2", "TMON"),
            "TCS70A106DL2": _etf("TCS70A106DL2", "TMON@"),
        },
        preferred={"TCSM99706DL2"},
    )
    assert mapping["TCS10A106DL2"] == "TCSM99706DL2"
    assert mapping["TCS70A106DL2"] == "TCS70A106DL2"


def test_usd_bond_uses_fx_not_one_to_one() -> None:
    """Облигация с номиналом в USD должна умножаться на курс, иначе «Минимум рисков» занижен."""
    t0 = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    figi = "TCS00A10E9Y0"
    operations = [
        SimpleNamespace(
            id=1,
            account_id=3,
            figi=figi,
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("4"),
            price=Decimal("92.55"),
            payment=Decimal("-310000"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
    ]
    instrument = SimpleNamespace(
        figi=figi,
        ticker=figi,
        isin=figi,
        currency="USD",
        instrument_type="bond",
        nominal=Decimal("1000"),
        nominal_currency="USD",
    )
    day = date(2026, 9, 11)
    rows = compute_snapshots(
        operations,
        {figi: instrument},
        {
            figi: {day: Decimal("92.55")},
            CURRENCY_FIGI["USD"]: {day: Decimal("84")},
        },
        {},
        day,
        day,
    )
    # 4 × 92.55% × 1000 USD × 84 ≈ 310968
    assert rows[0]["securities"] > Decimal("300000")
    assert rows[0]["securities"] < Decimal("400000")


def test_invest_box_value_is_fund_not_leftover_cash() -> None:
    """Инвесткопилка всегда в фонде: кэш из платежей не должен завышать историю."""
    t0 = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    figi = "TCSM99706DL2"
    operations = [
        SimpleNamespace(
            id=1,
            account_id=2,
            figi="",
            operation_type="OPERATION_TYPE_INPUT",
            quantity=Decimal("0"),
            price=Decimal("0"),
            payment=Decimal("1600"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
        SimpleNamespace(
            id=2,
            account_id=2,
            figi=figi,
            operation_type="OPERATION_TYPE_BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            payment=Decimal("-1000"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=t0,
            state="OPERATION_STATE_EXECUTED",
        ),
    ]
    instrument = _etf(figi, "TMON")
    rows = compute_snapshots(
        operations,
        {figi: instrument},
        {
            figi: {date(2026, 8, 31): Decimal("163.42"), date(2026, 9, 11): Decimal("164.23")},
        },
        {},
        date(2026, 8, 31),
        date(2026, 9, 11),
        account_types={2: "invest_box"},
    )
    by_day = {item["day"]: item for item in rows}
    august = by_day[date(2026, 8, 31)]
    september = by_day[date(2026, 9, 11)]
    assert august["cash"] == Decimal("0")
    assert august["securities"] == Decimal("1634.20")
    assert september["securities"] == Decimal("1642.30")
    assert september["value"] > august["value"]
