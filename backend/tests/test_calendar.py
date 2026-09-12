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


async def _empty_prices(*_args, **_kwargs):
    return {}
