from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db as db_module
from app.models import Account, BrokerConnection, Instrument, Operation, Position
from app.models.history import PortfolioSnapshot, PriceDaily
from app.schemas.history import HistoryOut, HistoryPointOut
from app.services.crypto import CryptoError, decrypt_secret
from app.services.invest_types import (
    BUY_TYPES,
    CASHFLOW_TYPES,
    CURRENCY_FIGI,
    SELL_TYPES,
    currency_code_of,
)
from app.services.portfolio import (
    is_bond,
    is_cash_position,
    money_str,
    quoted_unit_price,
    resolve_bond_nominal,
    to_rub,
    unique_positions,
)
from app.services.quotes import fetch_daily_candles, fetch_imoex
from app.services.xirr import moscow_day, moscow_today

logger = logging.getLogger("portfel.history")

ZERO = Decimal("0")
QTY_EPS = Decimal("0.00000001")
IMOEX = "IMOEX"
CANDLE_TIMEOUT = 30


def compute_snapshots(
    operations: list[Any],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    imoex: dict[date, Decimal],
    start: date,
    end: date,
) -> list[dict]:
    ordered = sorted(
        [item for item in operations if _executed(item)],
        key=lambda item: (getattr(item, "occurred_at"), getattr(item, "id", 0) or 0),
    )
    index = 0
    holdings: dict[tuple[int, str], tuple[Decimal, Decimal]] = {}
    cash_pay: dict[str, Decimal] = defaultdict(lambda: ZERO)
    snapshots: list[dict] = []
    invested = ZERO
    day = start
    while day <= end:
        while index < len(ordered) and moscow_day(ordered[index].occurred_at) <= day:
            invested += _apply_operation(ordered[index], holdings, cash_pay, closes, day)
            index += 1
        fx_prices = _fx_prices(closes, day)
        cash = _cash_rub(cash_pay, holdings, instruments, fx_prices)
        securities = _securities_rub(holdings, instruments, closes, day, fx_prices)
        snapshots.append(
            {
                "day": day,
                "value": cash + securities,
                "cash": cash,
                "securities": securities,
                "invested": invested,
                "imoex": imoex.get(day),
            }
        )
        day += timedelta(days=1)
    return snapshots


async def rebuild_history(connection_id: int, *, force: bool = False) -> None:
    async with db_module.SessionLocal() as session:
        connection = await session.get(BrokerConnection, connection_id)
        if connection is None:
            return
        today = moscow_today()
        if not force:
            last = await session.scalar(
                select(func.max(PortfolioSnapshot.day)).where(
                    PortfolioSnapshot.connection_id == connection.id
                )
            )
            if last == today:
                return
        await _rebuild(session, connection, today)


async def load_history(session: AsyncSession, connection: BrokerConnection | None) -> HistoryOut:
    if connection is None:
        return HistoryOut(building=False, points=[], xirr_percent=None, xirr_from=None)
    result = await session.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.connection_id == connection.id)
        .order_by(PortfolioSnapshot.day)
    )
    rows = list(result.scalars())
    points = [
        HistoryPointOut(
            day=item.day,
            value=money_str(item.value_rub),
            cash=money_str(item.cash_rub),
            securities=money_str(item.securities_rub),
            invested=money_str(item.invested_rub),
            imoex=money_str(item.imoex_close) if item.imoex_close is not None else None,
        )
        for item in rows
    ]
    last = rows[-1].day if rows else None
    building = last is None
    return HistoryOut(
        building=building,
        points=points,
        xirr_percent=None,
        xirr_from=None,
    )


async def _rebuild(session: AsyncSession, connection: BrokerConnection, today: date) -> None:
    ops_result = await session.execute(
        select(Operation)
        .join(Account)
        .where(Account.connection_id == connection.id)
        .order_by(Operation.occurred_at, Operation.id)
    )
    operations = list(ops_result.scalars())
    if not operations:
        await session.execute(
            delete(PortfolioSnapshot).where(PortfolioSnapshot.connection_id == connection.id)
        )
        await session.commit()
        return

    start = min(moscow_day(item.occurred_at) for item in operations)
    pos_result = await session.execute(
        select(Position).join(Account).where(Account.connection_id == connection.id)
    )
    positions = list(pos_result.scalars())
    figis = {item.figi for item in operations if item.figi}
    figis.update(item.figi for item in positions if item.figi)
    figis.update(figi for code, figi in CURRENCY_FIGI.items() if code != "RUB")
    instruments = await _instruments_by_figi(session, list(figis))
    candle_figis = [
        figi
        for figi in figis
        if figi and figi != IMOEX and not _is_cash_figi(figi, instruments.get(figi))
    ]
    candle_figis.extend(figi for code, figi in CURRENCY_FIGI.items() if code != "RUB")
    candle_figis = list(dict.fromkeys(candle_figis))

    fetched_any = False
    try:
        token = decrypt_secret(connection.token_encrypted)
    except CryptoError:
        token = ""
        logger.warning("Skip candle fetch, cannot decrypt token id=%s", connection.id)

    if token:
        for figi in candle_figis:
            from_day = await _last_price_day(session, figi)
            fetch_start = start if from_day is None else min(from_day, today)
            if from_day == today:
                continue
            try:
                candles = await asyncio.wait_for(
                    fetch_daily_candles(token, figi, fetch_start, today),
                    timeout=CANDLE_TIMEOUT,
                )
            except Exception:
                logger.warning("Candles failed figi=%s", figi, exc_info=True)
                continue
            if candles:
                fetched_any = True
                currency = (instruments[figi].currency if figi in instruments else "") or "RUB"
                await _store_prices(session, figi, candles, currency, "tinkoff")
            await asyncio.sleep(0.05)

    try:
        imoex_raw = await fetch_imoex(start, today)
    except Exception:
        logger.warning("IMOEX fetch failed", exc_info=True)
        imoex_raw = {}
    if imoex_raw:
        fetched_any = True
        await _store_prices(session, IMOEX, sorted(imoex_raw.items()), "RUB", "moex")

    stored = await _load_prices(session, [*candle_figis, IMOEX], start, today)
    if not fetched_any and not stored:
        await _snapshot_today_only(session, connection, positions, instruments, today)
        return

    closes = {figi: _ffill(series, start, today) for figi, series in stored.items() if figi != IMOEX}
    imoex = _ffill(stored.get(IMOEX, {}), start, today)
    rows = compute_snapshots(operations, instruments, closes, imoex, start, today)
    pin = _today_totals(positions, instruments, closes, today)
    if pin is not None and rows:
        rows[-1]["value"] = pin[0]
        rows[-1]["cash"] = pin[1]
        rows[-1]["securities"] = pin[2]

    await session.execute(
        delete(PortfolioSnapshot).where(PortfolioSnapshot.connection_id == connection.id)
    )
    for item in rows:
        session.add(
            PortfolioSnapshot(
                connection_id=connection.id,
                day=item["day"],
                value_rub=item["value"],
                cash_rub=item["cash"],
                securities_rub=item["securities"],
                invested_rub=item["invested"],
                imoex_close=item["imoex"],
            )
        )
    await session.commit()
    logger.info("History rebuilt id=%s days=%s", connection.id, len(rows))


async def _snapshot_today_only(
    session: AsyncSession,
    connection: BrokerConnection,
    positions: list[Position],
    instruments: dict[str, Instrument],
    today: date,
) -> None:
    pin = _today_totals(positions, instruments, {}, today)
    if pin is None:
        return
    await session.execute(
        delete(PortfolioSnapshot).where(PortfolioSnapshot.connection_id == connection.id)
    )
    session.add(
        PortfolioSnapshot(
            connection_id=connection.id,
            day=today,
            value_rub=pin[0],
            cash_rub=pin[1],
            securities_rub=pin[2],
            invested_rub=ZERO,
            imoex_close=None,
        )
    )
    await session.commit()


def _today_totals(
    positions: list[Position],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    today: date,
) -> tuple[Decimal, Decimal, Decimal] | None:
    if not positions:
        return None
    fx_prices: dict[str, Decimal] = {}
    for code, figi in CURRENCY_FIGI.items():
        if code == "RUB":
            continue
        series = closes.get(figi, {})
        if today in series:
            fx_prices[figi] = series[today]
    value = ZERO
    cash = ZERO
    for item in unique_positions(positions, instruments):
        instrument = instruments.get(item.figi)
        if is_cash_position(item, instrument):
            code = (
                currency_code_of(
                    figi=item.figi,
                    ticker=instrument.ticker if instrument else "",
                    fallback=item.current_price_currency or "RUB",
                )
                or "RUB"
            )
            amount = to_rub(item.quantity, code, fx_prices)
            cash += amount
            value += amount
            continue
        instrument_type = item.instrument_type or (instrument.instrument_type if instrument else "")
        series = closes.get(item.figi, {})
        raw = series.get(today, item.current_price or ZERO)
        nominal = instrument.nominal if instrument else ZERO
        nominal_ccy = (instrument.nominal_currency if instrument else "") or ""
        if is_bond(instrument_type) and raw <= Decimal("200"):
            nominal, nominal_ccy = resolve_bond_nominal(
                stored_nominal=nominal or ZERO,
                stored_currency=nominal_ccy,
                average=item.average_price or ZERO,
                prices=fx_prices,
            )
        current = quoted_unit_price(
            raw,
            instrument_type=instrument_type,
            nominal=nominal,
            average=item.average_price or ZERO,
        )
        currency = item.current_price_currency or (instrument.currency if instrument else "RUB") or "RUB"
        if is_bond(instrument_type) and nominal > 0 and raw <= Decimal("200"):
            currency = nominal_ccy or currency
        amount = to_rub(item.quantity * current, currency, fx_prices)
        value += amount
    return value, cash, value - cash


def _apply_operation(
    operation: Any,
    holdings: dict[tuple[int, str], tuple[Decimal, Decimal]],
    cash_pay: dict[str, Decimal],
    closes: dict[str, dict[date, Decimal]],
    day: date,
) -> Decimal:
    currency = getattr(operation, "currency", None) or "RUB"
    payment = Decimal(str(getattr(operation, "payment", 0) or 0))
    commission = Decimal(str(getattr(operation, "commission", 0) or 0))
    cash_pay[currency] += payment + commission
    invested = ZERO
    if (getattr(operation, "operation_type", "") or "") in CASHFLOW_TYPES:
        invested = to_rub(payment, currency, _fx_prices(closes, day))

    figi = getattr(operation, "figi", "") or ""
    op_type = getattr(operation, "operation_type", "") or ""
    if figi and op_type in BUY_TYPES | SELL_TYPES:
        key = (int(operation.account_id), str(figi))
        qty, avg = holdings.get(key, (ZERO, ZERO))
        add_qty = Decimal(str(getattr(operation, "quantity", 0) or 0))
        if op_type in BUY_TYPES and add_qty > 0:
            price = Decimal(str(getattr(operation, "price", 0) or 0))
            if price == 0:
                price = abs(payment) / add_qty if add_qty else ZERO
            new_qty = qty + add_qty
            avg = (qty * avg + add_qty * price) / new_qty if new_qty else ZERO
            holdings[key] = (new_qty, avg)
        elif op_type in SELL_TYPES:
            qty = qty - add_qty
            holdings[key] = (ZERO, ZERO) if qty <= QTY_EPS else (qty, avg)
    return invested


def _cash_rub(
    cash_pay: dict[str, Decimal],
    holdings: dict[tuple[int, str], tuple[Decimal, Decimal]],
    instruments: dict[str, Instrument],
    fx_prices: dict[str, Decimal],
) -> Decimal:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for currency, amount in cash_pay.items():
        totals[currency.upper()] += amount
    for (_account_id, figi), (qty, _avg) in holdings.items():
        if qty <= 0:
            continue
        instrument = instruments.get(figi)
        if not _is_cash_figi(figi, instrument):
            continue
        code = currency_code_of(
            figi=figi,
            ticker=instrument.ticker if instrument else "",
            fallback=instrument.currency if instrument else "RUB",
        )
        if code and code != "RUB":
            totals[code] += qty
    total = ZERO
    for currency, amount in totals.items():
        total += to_rub(amount, currency, fx_prices)
    return total


def _securities_rub(
    holdings: dict[tuple[int, str], tuple[Decimal, Decimal]],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    day: date,
    fx_prices: dict[str, Decimal],
) -> Decimal:
    by_figi: dict[str, tuple[Decimal, Decimal]] = {}
    for (_account_id, figi), (qty, avg) in holdings.items():
        if qty <= 0 or _is_cash_figi(figi, instruments.get(figi)):
            continue
        prev_qty, prev_avg = by_figi.get(figi, (ZERO, ZERO))
        new_qty = prev_qty + qty
        avg_price = (prev_qty * prev_avg + qty * avg) / new_qty if new_qty else ZERO
        by_figi[figi] = (new_qty, avg_price)

    total = ZERO
    for figi, (qty, avg) in by_figi.items():
        instrument = instruments.get(figi)
        instrument_type = instrument.instrument_type if instrument else ""
        raw = (closes.get(figi) or {}).get(day, avg)
        if raw <= 0:
            raw = avg
        stored_nominal = instrument.nominal if instrument else ZERO
        stored_ccy = (instrument.nominal_currency if instrument else "") or ""
        currency = (instrument.currency if instrument else "") or "RUB"
        if is_bond(instrument_type) and raw <= Decimal("200"):
            nominal, nominal_ccy = resolve_bond_nominal(
                stored_nominal=stored_nominal or ZERO,
                stored_currency=stored_ccy,
                average=avg,
                prices=fx_prices,
            )
            raw = quoted_unit_price(raw, instrument_type=instrument_type, nominal=nominal, average=avg)
            currency = nominal_ccy or currency
        total += to_rub(qty * raw, currency, fx_prices)
    return total


def _fx_prices(closes: dict[str, dict[date, Decimal]], day: date) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for _code, figi in CURRENCY_FIGI.items():
        series = closes.get(figi)
        if series and day in series and series[day] > 0:
            prices[figi] = series[day]
    return prices


def _ffill(series: dict[date, Decimal], start: date, end: date) -> dict[date, Decimal]:
    if not series:
        return {}
    last = series[min(series)]
    result: dict[date, Decimal] = {}
    day = start
    while day <= end:
        if day in series and series[day] > 0:
            last = series[day]
        result[day] = last
        day += timedelta(days=1)
    return result


def _is_cash_figi(figi: str, instrument: Instrument | None) -> bool:
    ticker = instrument.ticker if instrument else ""
    itype = (instrument.instrument_type if instrument else "") or ""
    if itype.lower() in {"currency", "currencies"}:
        return True
    return bool(currency_code_of(figi=figi, ticker=ticker or ""))


def _executed(operation: Any) -> bool:
    state = (getattr(operation, "state", "") or "").upper()
    return not state or "EXECUTED" in state


async def _last_price_day(session: AsyncSession, figi: str) -> date | None:
    return await session.scalar(select(func.max(PriceDaily.day)).where(PriceDaily.figi == figi))


async def _store_prices(
    session: AsyncSession,
    figi: str,
    candles: list[tuple[date, Decimal]],
    currency: str,
    source: str,
) -> None:
    if not candles:
        return
    days = [day for day, _close in candles]
    result = await session.execute(
        select(PriceDaily).where(PriceDaily.figi == figi, PriceDaily.day.in_(days))
    )
    existing = {item.day: item for item in result.scalars()}
    for day, close in candles:
        row = existing.get(day)
        if row is None:
            session.add(
                PriceDaily(figi=figi, day=day, close=close, currency=currency or "RUB", source=source)
            )
        else:
            row.close = close
            row.source = source
    await session.commit()


async def _load_prices(
    session: AsyncSession, figis: list[str], start: date, end: date
) -> dict[str, dict[date, Decimal]]:
    unique = [item for item in dict.fromkeys(figis) if item]
    if not unique:
        return {}
    result = await session.execute(
        select(PriceDaily).where(
            PriceDaily.figi.in_(unique),
            PriceDaily.day >= start,
            PriceDaily.day <= end,
        )
    )
    stored: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for item in result.scalars():
        stored[item.figi][item.day] = item.close
    return stored


async def _instruments_by_figi(session: AsyncSession, figis: list[str]) -> dict[str, Instrument]:
    unique = list({item for item in figis if item})
    if not unique:
        return {}
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(unique)))
    return {item.figi: item for item in result.scalars()}


def should_rebuild_in_request() -> bool:
    return not os.environ.get("PYTEST_CURRENT_TEST")
