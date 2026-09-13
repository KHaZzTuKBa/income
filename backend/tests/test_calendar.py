from datetime import date, datetime, timezone
from decimal import Decimal

from httpx import AsyncClient

from app.services.invest_types import ForecastDTO, OperationDTO
from tests.test_dashboard import _seed
from tests.test_sync import _payload


def _dividend() -> OperationDTO:
    return OperationDTO(
        broker_account_id="acc-broker",
        broker_operation_id="op-div",
        parent_operation_id="",
        figi="BBG004730N88",
        instrument_uid="uid-sber",
        operation_type="OPERATION_TYPE_DIVIDEND",
        name="Дивиденд SBER",
        state="OPERATION_STATE_EXECUTED",
        quantity=Decimal("10"),
        price=Decimal("0"),
        payment=Decimal("500"),
        commission=Decimal("0"),
        currency="RUB",
        occurred_at=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
    )


def _coupon() -> OperationDTO:
    return OperationDTO(
        broker_account_id="acc-broker",
        broker_operation_id="op-cpn",
        parent_operation_id="",
        figi="BOND1",
        instrument_uid="",
        operation_type="OPERATION_TYPE_COUPON",
        name="Купон",
        state="OPERATION_STATE_EXECUTED",
        quantity=Decimal("5"),
        price=Decimal("0"),
        payment=Decimal("80"),
        commission=Decimal("0"),
        currency="RUB",
        occurred_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
    )


async def test_calendar_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/calendar")
    assert response.status_code == 401


async def test_calendar_empty(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/calendar")
    assert response.status_code == 200
    body = response.json()
    assert body["received_12m"] == "0.00"
    assert body["received_all_time"] == "0.00"
    assert body["forecast_12m"] == "0.00"
    assert len(body["months"]) == 12
    assert body["events"] == []


async def test_calendar_received_and_forecast(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.operations.extend([_dividend(), _coupon()])

    async def fake_forecasts(_token, _instruments, _start, _end):
        return [
            ForecastDTO(
                figi="BBG004730N88",
                kind="dividend",
                status="declared",
                event_date=date(2026, 11, 20),
                amount_per_unit=Decimal("18.7"),
                currency="RUB",
            )
        ]

    monkeypatch.setattr("app.services.calendar.moscow_today", lambda: date(2026, 9, 12))
    monkeypatch.setattr("app.services.calendar.fetch_income_forecasts", fake_forecasts)
    monkeypatch.setattr("app.services.calendar.fetch_last_prices", _empty_prices)
    await _seed(auth_client, monkeypatch, payload, prices={})

    body = (await auth_client.get("/api/calendar")).json()
    assert body["received_12m"] == "580.00"
    assert body["received_all_time"] == "580.00"
    assert body["forecast_12m"] == "187.00"
    assert body["yield_percent"] == "6.93"

    november = next(item for item in body["months"] if item["year"] == 2026 and item["month"] == 11)
    assert november["upcoming"] == "187.00"

    tickers = {item["ticker"] for item in body["events"]}
    assert "SBER" in tickers
    declared = next(item for item in body["events"] if item["status"] == "declared")
    assert declared["amount_rub"] == "187.00"
    received = {item["kind"] for item in body["events"] if item["status"] == "received"}
    assert received == {"dividend", "coupon"}


async def test_calendar_skips_forecast_if_already_received(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.operations.append(
        OperationDTO(
            broker_account_id="acc-broker",
            broker_operation_id="op-div-same",
            parent_operation_id="",
            figi="BBG004730N88",
            instrument_uid="uid-sber",
            operation_type="OPERATION_TYPE_DIVIDEND",
            name="Дивиденд",
            state="OPERATION_STATE_EXECUTED",
            quantity=Decimal("10"),
            price=Decimal("0"),
            payment=Decimal("187"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
        )
    )

    async def fake_forecasts(_token, _instruments, _start, _end):
        return [
            ForecastDTO(
                figi="BBG004730N88",
                kind="dividend",
                status="declared",
                event_date=date(2026, 11, 20),
                amount_per_unit=Decimal("18.7"),
                currency="RUB",
            )
        ]

    monkeypatch.setattr("app.services.calendar.moscow_today", lambda: date(2026, 9, 12))
    monkeypatch.setattr("app.services.calendar.fetch_income_forecasts", fake_forecasts)
    monkeypatch.setattr("app.services.calendar.fetch_last_prices", _empty_prices)
    await _seed(auth_client, monkeypatch, payload, prices={})

    body = (await auth_client.get("/api/calendar")).json()
    upcoming = [item for item in body["events"] if item["status"] != "received"]
    assert upcoming == []
    assert body["forecast_12m"] == "0.00"
    assert body["received_12m"] == "0.00"
    assert body["received_all_time"] == "187.00"


async def test_calendar_all_time_includes_old_dividend(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.operations.append(
        OperationDTO(
            broker_account_id="acc-broker",
            broker_operation_id="op-div-old",
            parent_operation_id="",
            figi="BBG004730N88",
            instrument_uid="uid-sber",
            operation_type="OPERATION_TYPE_DIVIDEND",
            name="Старый дивиденд",
            state="OPERATION_STATE_EXECUTED",
            quantity=Decimal("10"),
            price=Decimal("0"),
            payment=Decimal("300"),
            commission=Decimal("0"),
            currency="RUB",
            occurred_at=datetime(2025, 8, 1, 12, 0, tzinfo=timezone.utc),
        )
    )
    payload.operations.append(_dividend())

    monkeypatch.setattr("app.services.calendar.moscow_today", lambda: date(2026, 9, 12))
    monkeypatch.setattr("app.services.calendar.fetch_income_forecasts", _empty_forecasts)
    monkeypatch.setattr("app.services.calendar.fetch_last_prices", _empty_prices)
    await _seed(auth_client, monkeypatch, payload, prices={})

    body = (await auth_client.get("/api/calendar")).json()
    assert body["received_12m"] == "500.00"
    assert body["received_all_time"] == "800.00"


async def test_calendar_payments_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/calendar/payments")
    assert response.status_code == 401


async def test_calendar_payments_history(auth_client: AsyncClient, monkeypatch) -> None:
    payload = _payload()
    payload.operations.extend(
        [
            _dividend(),
            _coupon(),
            OperationDTO(
                broker_account_id="acc-broker",
                broker_operation_id="op-div-week",
                parent_operation_id="",
                figi="BBG004730N88",
                instrument_uid="uid-sber",
                operation_type="OPERATION_TYPE_DIVIDEND",
                name="Дивиденд за неделю",
                state="OPERATION_STATE_EXECUTED",
                quantity=Decimal("10"),
                price=Decimal("0"),
                payment=Decimal("40"),
                commission=Decimal("0"),
                currency="RUB",
                occurred_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
            ),
        ]
    )

    monkeypatch.setattr("app.services.calendar.moscow_today", lambda: date(2026, 9, 12))
    monkeypatch.setattr("app.services.calendar.fetch_income_forecasts", _empty_forecasts)
    monkeypatch.setattr("app.services.calendar.fetch_last_prices", _empty_prices)
    await _seed(auth_client, monkeypatch, payload, prices={})
    await auth_client.get("/api/calendar")

    year_body = (await auth_client.get("/api/calendar/payments", params={"period": "1y"})).json()
    assert year_body["granularity"] == "month"
    assert year_body["total"] == "620.00"
    january = next(item for item in year_body["points"] if item["day"].startswith("2026-01-"))
    february = next(item for item in year_body["points"] if item["day"].startswith("2026-02-"))
    september = next(item for item in year_body["points"] if item["day"].startswith("2026-09-"))
    assert january["amount"] == "500.00"
    assert february["amount"] == "80.00"
    assert september["amount"] == "40.00"

    week_body = (await auth_client.get("/api/calendar/payments", params={"period": "week"})).json()
    assert week_body["granularity"] == "day"
    assert week_body["total"] == "40.00"
    assert len(week_body["points"]) == 7
    assert week_body["points"][0]["day"] == "2026-09-06"
    assert week_body["points"][-1]["day"] == "2026-09-12"
    assert next(item for item in week_body["points"] if item["day"] == "2026-09-10")["amount"] == "40.00"

    all_body = (await auth_client.get("/api/calendar/payments", params={"period": "all"})).json()
    assert all_body["from_day"] == "2026-01-15"
    assert all_body["to_day"] == "2026-09-12"
    assert all_body["points"][0]["day"] == "2026-01-31"
    assert all_body["total"] == "620.00"
    assert 2026 in all_body["years"]


async def _empty_forecasts(*_args, **_kwargs):
    return []


async def _empty_prices(*_args, **_kwargs):
    return {}
