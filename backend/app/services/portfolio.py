from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import db as db_module
from app.models import Account, BrokerConnection, Instrument, Operation, Position, User
from app.schemas.invest import DashboardOut, DashboardPositionOut
from app.services.crypto import CryptoError, decrypt_secret
from app.services.invest_types import (
    BUY_TYPES,
    CASHFLOW_TYPES,
    CURRENCY_FIGI,
    FIGI_TO_CURRENCY,
    SELL_TYPES,
    currency_code_of,
)
from app.services.quotes import fetch_last_prices
from app.services.sync import get_connection
from app.services.xirr import investor_cashflows, moscow_today, xirr_percent

logger = logging.getLogger("portfel.portfolio")

ZERO = Decimal("0")
MONEY = Decimal("0.01")
PRICE = Decimal("0.000001")
LIVE_TIMEOUT = 8
QTY_EPS = Decimal("0.00000001")


def money_str(value: Decimal) -> str:
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), "f")


def price_str(value: Decimal) -> str:
    quantized = value.quantize(PRICE, rounding=ROUND_HALF_UP)
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def remaining_lots(operations: Sequence[Any]) -> dict[tuple[int, str], tuple[Decimal, Decimal]]:
    """Средняя по оставшимся лотам: (account_id, figi) -> (qty, avg)."""
    ordered = sorted(
        operations,
        key=lambda item: (
            getattr(item, "occurred_at", datetime.min.replace(tzinfo=timezone.utc)),
            getattr(item, "id", 0) or 0,
        ),
    )
    state: dict[tuple[int, str], tuple[Decimal, Decimal]] = {}
    for operation in ordered:
        figi = getattr(operation, "figi", "") or ""
        if not figi:
            continue
        op_type = getattr(operation, "operation_type", "") or ""
        key = (int(operation.account_id), str(figi))
        qty, avg = state.get(key, (ZERO, ZERO))
        add_qty = Decimal(str(getattr(operation, "quantity", 0) or 0))
        if op_type in BUY_TYPES:
            if add_qty <= 0:
                continue
            price = Decimal(str(getattr(operation, "price", 0) or 0))
            if price == 0:
                payment = abs(Decimal(str(getattr(operation, "payment", 0) or 0)))
                price = payment / add_qty if add_qty else ZERO
            new_qty = qty + add_qty
            avg = (qty * avg + add_qty * price) / new_qty if new_qty else ZERO
            state[key] = (new_qty, avg)
        elif op_type in SELL_TYPES:
            qty = qty - add_qty
            if qty <= QTY_EPS:
                state[key] = (ZERO, ZERO)
            else:
                state[key] = (qty, avg)
    return state


PERCENT_QUOTE_MAX = Decimal("200")


def is_bond(instrument_type: str) -> bool:
    return (instrument_type or "").lower() in {"bond", "bonds"}


def quoted_unit_price(
    raw: Decimal,
    *,
    instrument_type: str,
    nominal: Decimal = ZERO,
    average: Decimal = ZERO,
) -> Decimal:
    """Котировка облигации на Мосбирже — % от номинала."""
    if raw <= 0 or not is_bond(instrument_type):
        return raw
    if raw > PERCENT_QUOTE_MAX:
        return raw
    if nominal > 0:
        return raw / Decimal("100") * nominal
    if average > PERCENT_QUOTE_MAX:
        return raw * Decimal("10")
    return raw


def resolve_bond_nominal(
    *,
    stored_nominal: Decimal,
    stored_currency: str,
    average: Decimal,
    prices: dict[str, Decimal],
) -> tuple[Decimal, str]:
    if stored_nominal > 0:
        return stored_nominal, stored_currency or "RUB"
    usd_rate = prices.get(CURRENCY_FIGI["USD"])
    if usd_rate and usd_rate > Decimal("2") and average > 0:
        implied = average / usd_rate
        if Decimal("40") <= implied <= Decimal("200"):
            return Decimal("100"), "USD"
        if Decimal("400") <= implied <= Decimal("2000"):
            return Decimal("1000"), "USD"
    return Decimal("1000"), "RUB"


def is_cash_position(position: Position, instrument: Instrument | None) -> bool:
    instrument_type = (position.instrument_type or "").lower()
    if instrument_type in {"currency", "currencies"}:
        return True
    ticker = instrument.ticker if instrument else ""
    return bool(currency_code_of(figi=position.figi, ticker=ticker or ""))


def cash_currency(position: Position, instrument: Instrument | None) -> str:
    ticker = instrument.ticker if instrument else ""
    return (
        currency_code_of(
            figi=position.figi,
            ticker=ticker or "",
            fallback=position.current_price_currency or position.average_price_currency or "RUB",
        )
        or "RUB"
    )


def _cash_quality(position: Position, instrument: Instrument | None) -> tuple:
    code = cash_currency(position, instrument)
    return (
        1 if position.figi in FIGI_TO_CURRENCY else 0,
        1 if (position.current_price_currency or "").upper() == code else 0,
        position.quantity or ZERO,
    )


def unique_positions(
    positions: list[Position], instruments: dict[str, Instrument]
) -> list[Position]:
    selected: list[Position] = []
    cash_index: dict[tuple[int, str], int] = {}
    for item in positions:
        if item.quantity <= 0:
            continue
        instrument = instruments.get(item.figi)
        if not is_cash_position(item, instrument):
            selected.append(item)
            continue
        key = (item.account_id, cash_currency(item, instrument))
        existing = cash_index.get(key)
        if existing is None:
            cash_index[key] = len(selected)
            selected.append(item)
            continue
        if _cash_quality(item, instrument) > _cash_quality(
            selected[existing], instruments.get(selected[existing].figi)
        ):
            selected[existing] = item
    return selected


def fx_to_rub(currency: str, prices: dict[str, Decimal]) -> Decimal:
    code = (currency or "RUB").upper()
    if code == "RUB":
        return Decimal("1")
    figi = CURRENCY_FIGI.get(code)
    if not figi:
        return Decimal("1")
    rate = prices.get(figi)
    if rate is None or rate <= 0:
        return Decimal("1")
    return rate


def to_rub(amount: Decimal, currency: str, prices: dict[str, Decimal]) -> Decimal:
    return amount * fx_to_rub(currency, prices)


def cashflow_invested(operations: Iterable[Any], prices: dict[str, Decimal]) -> Decimal:
    total = ZERO
    for operation in operations:
        if (getattr(operation, "operation_type", "") or "") not in CASHFLOW_TYPES:
            continue
        payment = Decimal(str(getattr(operation, "payment", 0) or 0))
        currency = getattr(operation, "currency", None) or "RUB"
        total += to_rub(payment, currency, prices)
    return total


def _empty_dashboard() -> DashboardOut:
    return DashboardOut(
        value="0.00",
        invested="0.00",
        profit="0.00",
        profit_percent=None,
        cash="0.00",
        prices_as_of=None,
        prices_live=False,
        history_from=None,
        invested_missing=False,
        xirr_percent=None,
        xirr_from=None,
        positions=[],
    )


async def build_dashboard(session: AsyncSession, user: User, *, live: bool = True) -> DashboardOut:
    connection = await get_connection(session, user.id)
    if connection is None:
        return _empty_dashboard()

    result = await session.execute(
        select(Position)
        .join(Account)
        .where(Account.connection_id == connection.id)
        .options(selectinload(Position.account))
        .order_by(Position.id)
    )
    positions = list(result.scalars())

    ops_result = await session.execute(
        select(Operation)
        .join(Account)
        .where(Account.connection_id == connection.id)
        .order_by(Operation.occurred_at, Operation.id)
    )
    operations = list(ops_result.scalars())

    figis = [item.figi for item in positions if item.figi]
    instruments = await _instruments_by_figi(session, figis)

    prices: dict[str, Decimal] = {}
    for item in positions:
        if item.figi and item.current_price:
            prices[item.figi] = item.current_price

    prices_live = False
    if live and connection.token_encrypted:
        live_prices = await _live_prices(connection, [*figis, *CURRENCY_FIGI.values()])
        if live_prices:
            prices.update(live_prices)
            prices_live = True

    lots = remaining_lots(operations)
    invested = cashflow_invested(operations, prices)
    if live and connection.token_encrypted:
        await _fill_missing_nominals(session, connection, instruments, positions)

    drafts: list[dict] = []
    total_value = ZERO
    total_cash = ZERO

    for item in unique_positions(positions, instruments):
        instrument = instruments.get(item.figi)
        cash = is_cash_position(item, instrument)
        instrument_type = item.instrument_type or (instrument.instrument_type if instrument else "")
        ops_avg = lots.get((item.account_id, item.figi), (ZERO, ZERO))[1]
        if not cash and ops_avg > 0:
            average = ops_avg
            average_source = "operations"
        else:
            average = item.average_price or ZERO
            average_source = "broker"

        if cash:
            current = Decimal("1")
            current_currency = cash_currency(item, instrument)
            average = Decimal("1")
            average_currency = current_currency
        else:
            raw_current = prices.get(item.figi, item.current_price or ZERO)
            raw_average = average
            stored_nominal = instrument.nominal if instrument else ZERO
            stored_ccy = (instrument.nominal_currency if instrument else "") or ""
            if is_bond(instrument_type) and raw_current <= PERCENT_QUOTE_MAX:
                nominal, nominal_currency = resolve_bond_nominal(
                    stored_nominal=stored_nominal or ZERO,
                    stored_currency=stored_ccy,
                    average=raw_average,
                    prices=prices,
                )
            else:
                nominal, nominal_currency = stored_nominal or ZERO, stored_ccy
            current = quoted_unit_price(
                raw_current,
                instrument_type=instrument_type,
                nominal=nominal,
                average=raw_average,
            )
            average = quoted_unit_price(
                raw_average,
                instrument_type=instrument_type,
                nominal=nominal,
                average=ZERO,
            )
            current_currency = item.current_price_currency or "RUB"
            average_currency = item.average_price_currency or current_currency
            if is_bond(instrument_type) and nominal > 0:
                if raw_current <= PERCENT_QUOTE_MAX:
                    current_currency = nominal_currency or current_currency
                if raw_average <= PERCENT_QUOTE_MAX:
                    average_currency = nominal_currency or average_currency

        value = to_rub(item.quantity * current, current_currency, prices)
        cost = to_rub(item.quantity * average, average_currency, prices)
        pnl = ZERO if cash else value - cost
        pnl_percent = None
        if not cash and cost != 0:
            pnl_percent = money_str(pnl / cost * Decimal("100"))

        if cash:
            ticker = current_currency
            name = instrument.name if instrument and instrument.name else current_currency
        else:
            ticker = instrument.ticker if instrument and instrument.ticker else item.figi
            name = instrument.name if instrument and instrument.name else item.figi
        drafts.append(
            {
                "account_id": item.account_id,
                "account_name": item.account.name or item.account.broker_account_id,
                "figi": item.figi,
                "ticker": ticker,
                "name": name,
                "instrument_type": item.instrument_type,
                "quantity": price_str(item.quantity),
                "average_price": price_str(average),
                "average_price_currency": average_currency,
                "current_price": price_str(current),
                "current_price_currency": current_currency,
                "value": money_str(value),
                "cost": money_str(cost),
                "pnl": money_str(pnl),
                "pnl_percent": pnl_percent,
                "is_cash": cash,
                "average_source": average_source,
                "_value": value,
            }
        )
        total_value += value
        if cash:
            total_cash += value

    rows: list[DashboardPositionOut] = []
    for draft in drafts:
        value = draft.pop("_value")
        share = money_str(value / total_value * Decimal("100")) if total_value > 0 else "0.00"
        rows.append(DashboardPositionOut(share=share, **draft))

    rows.sort(key=lambda item: (item.is_cash, -Decimal(item.value)))

    profit = total_value - invested
    profit_percent = None
    if invested != 0:
        profit_percent = money_str(profit / invested * Decimal("100"))

    today = moscow_today()
    annual = xirr_percent(operations, prices, today, total_value, to_rub)
    xirr_from = None
    if annual is not None:
        flows = investor_cashflows(operations, prices, today, total_value, to_rub)
        dates = [day for day, amount in flows[:-1] if amount != 0]
        xirr_from = min(dates) if dates else None

    return DashboardOut(
        value=money_str(total_value),
        invested=money_str(invested),
        profit=money_str(profit),
        profit_percent=profit_percent,
        cash=money_str(total_cash),
        prices_as_of=datetime.now(timezone.utc),
        prices_live=prices_live,
        history_from=connection.history_from,
        invested_missing=invested == 0 and total_value > 0,
        xirr_percent=money_str(annual) if annual is not None else None,
        xirr_from=xirr_from,
        positions=rows,
    )


async def refresh_stored_prices() -> None:
    async with db_module.SessionLocal() as session:
        result = await session.execute(select(BrokerConnection))
        connections = list(result.scalars())

    for connection in connections:
        if connection.status == "running":
            continue
        try:
            token = decrypt_secret(connection.token_encrypted)
        except CryptoError:
            logger.warning("Skip price refresh, cannot decrypt token id=%s", connection.id)
            continue
        async with db_module.SessionLocal() as session:
            conn = await session.get(BrokerConnection, connection.id)
            if conn is None or conn.status == "running":
                continue
            pos_result = await session.execute(
                select(Position).join(Account).where(Account.connection_id == conn.id)
            )
            positions = list(pos_result.scalars())
            figis = [item.figi for item in positions if item.figi]
            if not figis:
                continue
            try:
                prices = await fetch_last_prices(token, [*figis, *CURRENCY_FIGI.values()])
            except Exception:
                logger.exception("Live prices failed for connection id=%s", conn.id)
                continue
            inst_result = await session.execute(
                select(Instrument).where(Instrument.figi.in_(figis))
            )
            instruments = {item.figi: item for item in inst_result.scalars()}
            changed = False
            for item in positions:
                if is_cash_position(item, instruments.get(item.figi)):
                    continue
                if item.figi in prices:
                    item.current_price = prices[item.figi]
                    changed = True
            if changed:
                await session.commit()
            logger.info("Refreshed prices for connection id=%s", conn.id)


async def _fill_missing_nominals(
    session: AsyncSession,
    connection: BrokerConnection,
    instruments: dict[str, Instrument],
    positions: list[Position],
) -> None:
    needed: list[Instrument] = []
    seen: set[str] = set()
    for item in positions:
        instrument = instruments.get(item.figi)
        if instrument is None or instrument.figi in seen:
            continue
        itype = item.instrument_type or instrument.instrument_type
        if is_bond(itype) and (instrument.nominal or ZERO) <= 0:
            needed.append(instrument)
            seen.add(instrument.figi)
    if not needed:
        return
    try:
        from app.services.invest import fetch_instrument_nominals

        token = decrypt_secret(connection.token_encrypted)
        nominals = await asyncio.wait_for(
            fetch_instrument_nominals(token, [item.figi for item in needed]),
            timeout=15,
        )
    except Exception:
        logger.warning("Bond nominals unavailable for connection id=%s", connection.id, exc_info=True)
        return
    changed = False
    for instrument in needed:
        if instrument.figi not in nominals:
            continue
        instrument.nominal, instrument.nominal_currency = nominals[instrument.figi]
        changed = True
    if changed:
        await session.commit()


async def _live_prices(connection: BrokerConnection, figis: list[str]) -> dict[str, Decimal]:
    try:
        token = decrypt_secret(connection.token_encrypted)
        return await asyncio.wait_for(fetch_last_prices(token, figis), timeout=LIVE_TIMEOUT)
    except Exception:
        logger.warning("Live prices unavailable for connection id=%s", connection.id, exc_info=True)
        return {}


async def _instruments_by_figi(session: AsyncSession, figis: list[str]) -> dict[str, Instrument]:
    unique = list({item for item in figis if item})
    if not unique:
        return {}
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(unique)))
    return {item.figi: item for item in result.scalars()}
