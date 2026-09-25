from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Instrument, User
from app.schemas.invest import DashboardPositionOut
from app.schemas.sector import SectorHoldingOut, SectorPaperOut, SectorPieOut, SectorSliceOut, SectorsOut
from app.services.portfolio import build_dashboard, money_str
from app.services.sync import get_connection

ZERO = Decimal("0")
HUNDRED = Decimal("100")

SECTOR_LABELS = {
    "financial": "Финансы",
    "financials": "Финансы",
    "energy": "Энергетика",
    "materials": "Материалы",
    "industrials": "Промышленность",
    "consumer": "Потребительский сектор",
    "consumer_staples": "Товары первой необходимости",
    "consumer_discretionary": "Потребительский сектор",
    "consumer_cyclical": "Потребительский сектор",
    "healthcare": "Здравоохранение",
    "health_care": "Здравоохранение",
    "it": "IT",
    "information_technology": "IT",
    "technology": "IT",
    "telecom": "Телекоммуникации",
    "telecommunications": "Телекоммуникации",
    "telecommunication": "Телекоммуникации",
    "utilities": "Коммунальные услуги",
    "real_estate": "Недвижимость",
    "government": "Гос. бумаги",
    "other": "Другое",
    "green_energy": "Зелёная энергетика",
    "ecomaterials": "Экоматериалы",
}


def normalize_sector(raw: str | None) -> str:
    return (raw or "").strip()


def sector_label(raw: str | None) -> str:
    key = normalize_sector(raw)
    if not key:
        return "Без отрасли"
    mapped = SECTOR_LABELS.get(key.lower().replace("-", "_").replace(" ", "_"))
    return mapped if mapped else key


def _position_value(position: DashboardPositionOut) -> Decimal:
    return Decimal(position.value)


async def build_sectors(session: AsyncSession, user: User) -> SectorsOut:
    connection = await get_connection(session, user.id)
    if connection is None:
        return SectorsOut(pies=[], holdings=[])

    dashboard = await build_dashboard(session, user)
    papers = [item for item in dashboard.positions if not item.is_cash]
    figis = [item.figi for item in papers if item.figi]
    instruments = await _instruments_by_figi(session, figis)

    accounts_result = await session.execute(
        select(Account).where(Account.connection_id == connection.id).order_by(Account.id)
    )
    accounts = list(accounts_result.scalars())

    pies = [_make_pie("all", None, "Все счета", papers, instruments)]
    for account in accounts:
        scoped = [item for item in papers if item.account_id == account.id]
        label = account.name or account.broker_account_id
        pies.append(_make_pie(f"account:{account.id}", account.id, label, scoped, instruments))

    return SectorsOut(pies=pies, holdings=_holdings(papers, instruments))


def _make_pie(
    key: str,
    account_id: int | None,
    label: str,
    positions: list[DashboardPositionOut],
    instruments: dict[str, Instrument],
) -> SectorPieOut:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    papers: dict[str, dict[str, tuple[str, str, Decimal]]] = defaultdict(dict)
    total = ZERO
    for position in positions:
        sector = _sector_of(position.figi, instruments)
        amount = _position_value(position)
        totals[sector] += amount
        total += amount
        if not position.figi:
            continue
        existing = papers[sector].get(position.figi)
        if existing is None:
            papers[sector][position.figi] = (position.ticker, position.name, amount)
        else:
            ticker, name, current = existing
            papers[sector][position.figi] = (ticker, name, current + amount)

    slices: list[SectorSliceOut] = []
    for sector, amount in totals.items():
        holdings = [
            SectorPaperOut(
                figi=figi,
                ticker=ticker,
                name=name,
                value=money_str(value),
                share=money_str(value / total * HUNDRED) if total > 0 else "0.00",
            )
            for figi, (ticker, name, value) in papers[sector].items()
        ]
        holdings.sort(key=lambda item: (-Decimal(item.value), item.ticker, item.figi))
        slices.append(
            SectorSliceOut(
                key=sector,
                label=sector_label(sector),
                value=money_str(amount),
                share=money_str(amount / total * HUNDRED) if total > 0 else "0.00",
                holdings_count=len(holdings),
                holdings=holdings,
            )
        )
    slices.sort(key=lambda item: (item.key == "", -Decimal(item.value), item.label))
    return SectorPieOut(
        key=key,
        account_id=account_id,
        label=label,
        total=money_str(total),
        slices=slices,
    )


def _holdings(
    positions: list[DashboardPositionOut],
    instruments: dict[str, Instrument],
) -> list[SectorHoldingOut]:
    values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    meta: dict[str, tuple[str, str, str]] = {}
    for position in positions:
        if not position.figi:
            continue
        values[position.figi] += _position_value(position)
        if position.figi in meta:
            continue
        sector = _sector_of(position.figi, instruments)
        meta[position.figi] = (position.ticker, position.name, sector)
    rows = [
        SectorHoldingOut(
            figi=figi,
            ticker=ticker,
            name=name,
            sector=sector,
            sector_label=sector_label(sector),
            value=money_str(values[figi]),
        )
        for figi, (ticker, name, sector) in meta.items()
    ]
    rows.sort(key=lambda item: (-Decimal(item.value), item.ticker, item.figi))
    return rows


def _sector_of(figi: str, instruments: dict[str, Instrument]) -> str:
    instrument = instruments.get(figi)
    if instrument is None:
        return ""
    return normalize_sector(instrument.sector)


async def _instruments_by_figi(session: AsyncSession, figis: list[str]) -> dict[str, Instrument]:
    unique = list({item for item in figis if item})
    if not unique:
        return {}
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(unique)))
    return {item.figi: item for item in result.scalars()}
