from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app import db as db_module
from app.models import Instrument
from app.services.invest_types import InstrumentDTO, InvestPayload, PositionDTO
from app.services.sectors import sector_label
from tests.test_dashboard import _seed
from tests.test_sync import _payload


def _with_sber_sector() -> InvestPayload:
    payload = _payload()
    for item in payload.instruments:
        if item.ticker == "SBER":
            item.sector = "financial"
    return payload


def _with_two_sectors() -> InvestPayload:
    payload = _with_sber_sector()
    payload.positions.append(
        PositionDTO(
            broker_account_id="acc-iis",
            figi="BBG004730RP0",
            instrument_uid="uid-gazp",
            instrument_type="share",
            quantity=Decimal("5"),
            average_price=Decimal("140"),
            average_price_currency="RUB",
            current_price=Decimal("150"),
            current_price_currency="RUB",
        )
    )
    payload.instruments.append(
        InstrumentDTO(
            figi="BBG004730RP0",
            ticker="GAZP",
            name="Газпром",
            instrument_type="share",
            currency="RUB",
            sector="energy",
        )
    )
    return payload


def _pies(body: dict) -> dict[str, dict]:
    return {item["label"]: item for item in body["pies"]}


async def test_sectors_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/sectors")
    assert response.status_code == 401


async def test_sectors_empty_without_token(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/sectors")
    assert response.status_code == 200
    assert response.json() == {"pies": [], "holdings": []}


def test_sector_label_known_and_unknown() -> None:
    assert sector_label("financial") == "Финансы"
    assert sector_label("energy") == "Энергетика"
    assert sector_label("") == "Без отрасли"
    assert sector_label(None) == "Без отрасли"
    assert sector_label("custom-sector") == "custom-sector"


async def test_sectors_exclude_cash_and_split_accounts(auth_client: AsyncClient, monkeypatch) -> None:
    await _seed(auth_client, monkeypatch, _with_sber_sector(), prices={})

    body = (await auth_client.get("/api/sectors")).json()
    pies = _pies(body)
    assert set(pies) == {"Все счета", "Брокерский", "ИИС"}

    overall = pies["Все счета"]
    assert overall["key"] == "all"
    assert overall["account_id"] is None
    assert overall["total"] == "2700.00"
    assert len(overall["slices"]) == 1
    slice_row = overall["slices"][0]
    assert slice_row["key"] == "financial"
    assert slice_row["label"] == "Финансы"
    assert slice_row["value"] == "2700.00"
    assert slice_row["share"] == "100.00"
    assert slice_row["holdings_count"] == 1
    assert slice_row["holdings"][0]["ticker"] == "SBER"
    assert slice_row["holdings"][0]["value"] == "2700.00"
    assert slice_row["holdings"][0]["share"] == "100.00"

    broker = pies["Брокерский"]
    assert broker["total"] == "2700.00"
    assert broker["slices"][0]["key"] == "financial"

    iis = pies["ИИС"]
    assert iis["total"] == "0.00"
    assert iis["slices"] == []

    assert [item["ticker"] for item in body["holdings"]] == ["SBER"]
    assert body["holdings"][0]["value"] == "2700.00"
    assert body["holdings"][0]["sector"] == "financial"

    async with db_module.SessionLocal() as session:
        instrument = (
            await session.execute(select(Instrument).where(Instrument.figi == "BBG004730N88"))
        ).scalar_one()
        assert instrument.sector == "financial"


async def test_sectors_two_accounts_two_sectors(auth_client: AsyncClient, monkeypatch) -> None:
    await _seed(auth_client, monkeypatch, _with_two_sectors(), prices={})

    body = (await auth_client.get("/api/sectors")).json()
    pies = _pies(body)

    overall = pies["Все счета"]
    assert overall["total"] == "3450.00"
    by_key = {item["key"]: item for item in overall["slices"]}
    assert by_key["financial"]["value"] == "2700.00"
    assert by_key["financial"]["share"] == "78.26"
    assert by_key["energy"]["value"] == "750.00"
    assert by_key["energy"]["share"] == "21.74"
    assert by_key["energy"]["label"] == "Энергетика"

    assert pies["Брокерский"]["total"] == "2700.00"
    assert pies["ИИС"]["total"] == "750.00"
    assert pies["ИИС"]["slices"][0]["key"] == "energy"

    tickers = {item["ticker"]: item for item in body["holdings"]}
    assert tickers["SBER"]["value"] == "2700.00"
    assert tickers["GAZP"]["sector"] == "energy"


async def test_sectors_unknown_without_sector(auth_client: AsyncClient, monkeypatch) -> None:
    await _seed(auth_client, monkeypatch, _payload(), prices={})

    body = (await auth_client.get("/api/sectors")).json()
    slice_row = body["pies"][0]["slices"][0]
    assert slice_row["key"] == ""
    assert slice_row["label"] == "Без отрасли"
