from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db as db_module
from app.models import Accrual, Account, BrokerConnection, Instrument, Operation, Position, User
from app.schemas.calendar import (
    CalendarEventOut,
    CalendarMonthOut,
    CalendarOut,
    PaymentHistoryOut,
    PaymentHistoryPointOut,
)
from app.services.crypto import CryptoError, decrypt_secret
from app.services.history import resolve_history_window
from app.services.invest import fetch_income_forecasts
from app.services.invest_types import CURRENCY_FIGI, INCOME_TYPES
from app.services.portfolio import is_cash_position, money_str, to_rub
from app.services.quotes import fetch_last_prices
from app.services.sync import get_connection

logger = logging.getLogger("portfel.calendar")

MOSCOW = ZoneInfo("Europe/Moscow")
ZERO = Decimal("0")
STALE_AFTER = timedelta(hours=12)
FORECAST_TIMEOUT = 90


def moscow_today() -> date:
    return datetime.now(MOSCOW).date()


def add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    if month == 12:
        days = (date(year + 1, 1, 1) - date(year, 12, 1)).days
    else:
        days = (date(year, month + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(value.day, days))


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


async def build_calendar(
    session: AsyncSession,
    user: User,
    *,
    today: date | None = None,
    force_refresh: bool = False,
) -> CalendarOut:
    today = today or moscow_today()
    connection = await get_connection(session, user.id)
    if connection is None:
        return _empty_calendar(today)

    prices = await _fx_prices(connection)
    await _rebuild_received(session, connection, prices)
    await _maybe_rebuild_forecasts(session, connection, prices, today, force=force_refresh)

    result = await session.execute(
        select(Accrual)
        .where(Accrual.connection_id == connection.id)
        .order_by(Accrual.event_date, Accrual.id)
    )
    accruals = list(result.scalars())
    securities_value = await _securities_value(session, connection.id, prices)
    return _assemble(accruals, today, securities_value)


async def refresh_all_forecasts() -> None:
    async with db_module.SessionLocal() as session:
        result = await session.execute(select(BrokerConnection))
        connections = list(result.scalars())
    for connection in connections:
        if connection.status == "running":
            continue
        async with db_module.SessionLocal() as session:
            conn = await session.get(BrokerConnection, connection.id)
            if conn is None or conn.status == "running":
                continue
            try:
                prices = await _fx_prices(conn)
                await _maybe_rebuild_forecasts(session, conn, prices, moscow_today(), force=True)
            except Exception:
                logger.exception("Calendar forecast refresh failed id=%s", connection.id)


def _empty_calendar(today: date) -> CalendarOut:
    months = []
    start = month_start(today)
    for offset in range(12):
        cursor = add_months(start, offset)
        months.append(
            CalendarMonthOut(
                year=cursor.year,
                month=cursor.month,
                received="0.00",
                upcoming="0.00",
                total="0.00",
            )
        )
    return CalendarOut(
        received_12m="0.00",
        received_all_time="0.00",
        forecast_12m="0.00",
        securities_value="0.00",
        yield_percent=None,
        forecasts_as_of=None,
        months=months,
        events=[],
    )


async def _rebuild_received(
    session: AsyncSession, connection: BrokerConnection, prices: dict[str, Decimal]
) -> None:
    await session.execute(delete(Accrual).where(Accrual.connection_id == connection.id, Accrual.status == "received"))
    ops = await session.execute(
        select(Operation)
        .join(Account)
        .where(
            Account.connection_id == connection.id,
            Operation.operation_type.in_(INCOME_TYPES),
        )
    )
    operations = list(ops.scalars())
    instruments = await _instruments_by_figi(session, [item.figi for item in operations if item.figi])
    now = datetime.now(timezone.utc)
    for operation in operations:
        state = (operation.state or "").upper()
        if state and "EXECUTED" not in state:
            continue
        payment = abs(operation.payment or ZERO)
        if payment == 0:
            continue
        instrument = instruments.get(operation.figi)
        kind = "coupon" if "COUPON" in (operation.operation_type or "") else "dividend"
        event_date = operation.occurred_at
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        day = event_date.astimezone(MOSCOW).date()
        session.add(
            Accrual(
                connection_id=connection.id,
                figi=operation.figi or "",
                kind=kind,
                status="received",
                event_date=day,
                amount=payment,
                currency=operation.currency or "RUB",
                amount_rub=to_rub(payment, operation.currency or "RUB", prices),
                quantity=operation.quantity or ZERO,
                source="operations",
                source_key=f"op:{operation.account_id}:{operation.broker_operation_id}",
                ticker=(instrument.ticker if instrument and instrument.ticker else "") or operation.figi,
                name=(instrument.name if instrument and instrument.name else "") or operation.name,
                updated_at=now,
            )
        )
    await session.commit()


async def _maybe_rebuild_forecasts(
    session: AsyncSession,
    connection: BrokerConnection,
    prices: dict[str, Decimal],
    today: date,
    *,
    force: bool,
) -> None:
    if not force and not await _forecasts_stale(session, connection.id):
        return
    try:
        token = decrypt_secret(connection.token_encrypted)
    except CryptoError:
        logger.warning("Skip calendar forecasts, cannot decrypt token id=%s", connection.id)
        return

    positions, instruments = await _open_positions(session, connection.id)
    qty_by_figi: dict[str, Decimal] = defaultdict(lambda: ZERO)
    types: dict[str, str] = {}
    for position, instrument in positions:
        qty_by_figi[position.figi] += position.quantity or ZERO
        types[position.figi] = position.instrument_type or (instrument.instrument_type if instrument else "")

    start = datetime.combine(today, datetime.min.time(), tzinfo=MOSCOW).astimezone(timezone.utc)
    end = datetime.combine(add_months(today, 12), datetime.min.time(), tzinfo=MOSCOW).astimezone(timezone.utc)
    try:
        forecasts = await asyncio.wait_for(
            fetch_income_forecasts(token, [(figi, types[figi]) for figi in qty_by_figi], start, end),
            timeout=FORECAST_TIMEOUT,
        )
    except Exception:
        logger.exception("Income forecasts failed for connection id=%s", connection.id)
        return

    received_keys = {
        (item.figi, item.kind, item.event_date)
        for item in (
            await session.execute(
                select(Accrual).where(Accrual.connection_id == connection.id, Accrual.status == "received")
            )
        ).scalars()
    }
    await session.execute(
        delete(Accrual).where(
            Accrual.connection_id == connection.id,
            Accrual.status.in_(("declared", "forecast")),
        )
    )
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    for item in forecasts:
        if item.event_date < today or item.event_date >= add_months(today, 12):
            continue
        if (item.figi, item.kind, item.event_date) in received_keys:
            continue
        quantity = qty_by_figi.get(item.figi, ZERO)
        if quantity <= 0 or item.amount_per_unit == 0:
            continue
        source_key = f"fc:{item.kind}:{item.figi}:{item.event_date.isoformat()}"
        if source_key in seen:
            continue
        seen.add(source_key)
        amount = item.amount_per_unit * quantity
        instrument = instruments.get(item.figi)
        session.add(
            Accrual(
                connection_id=connection.id,
                figi=item.figi,
                kind=item.kind,
                status=item.status,
                event_date=item.event_date,
                amount=amount,
                currency=item.currency or "RUB",
                amount_rub=to_rub(amount, item.currency or "RUB", prices),
                quantity=quantity,
                source="tinkoff",
                source_key=source_key,
                ticker=(instrument.ticker if instrument and instrument.ticker else "") or item.figi,
                name=(instrument.name if instrument and instrument.name else "") or item.figi,
                updated_at=now,
            )
        )
    await session.commit()


async def _forecasts_stale(session: AsyncSession, connection_id: int) -> bool:
    latest = await session.scalar(
        select(func.max(Accrual.updated_at)).where(
            Accrual.connection_id == connection_id,
            Accrual.status.in_(("declared", "forecast")),
        )
    )
    if latest is None:
        return True
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - latest > STALE_AFTER


async def _fx_prices(connection: BrokerConnection) -> dict[str, Decimal]:
    try:
        token = decrypt_secret(connection.token_encrypted)
        return await asyncio.wait_for(fetch_last_prices(token, list(CURRENCY_FIGI.values())), timeout=8)
    except Exception:
        logger.warning("FX prices unavailable for calendar id=%s", connection.id, exc_info=True)
        return {}


async def _open_positions(
    session: AsyncSession, connection_id: int
) -> tuple[list[tuple[Position, Instrument | None]], dict[str, Instrument]]:
    result = await session.execute(
        select(Position).join(Account).where(Account.connection_id == connection_id)
    )
    positions = list(result.scalars())
    instruments = await _instruments_by_figi(session, [item.figi for item in positions if item.figi])
    opened: list[tuple[Position, Instrument | None]] = []
    for item in positions:
        if item.quantity <= 0:
            continue
        instrument = instruments.get(item.figi)
        if is_cash_position(item, instrument):
            continue
        opened.append((item, instrument))
    return opened, instruments


async def _securities_value(
    session: AsyncSession, connection_id: int, prices: dict[str, Decimal]
) -> Decimal:
    opened, _instruments = await _open_positions(session, connection_id)
    total = ZERO
    for position, instrument in opened:
        currency = position.current_price_currency or (instrument.currency if instrument else "RUB") or "RUB"
        price = prices.get(position.figi, position.current_price or ZERO)
        if price == 0:
            price = position.current_price or ZERO
        total += to_rub(position.quantity * price, currency, prices)
    return total


async def _instruments_by_figi(session: AsyncSession, figis: list[str]) -> dict[str, Instrument]:
    unique = list({item for item in figis if item})
    if not unique:
        return {}
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(unique)))
    return {item.figi: item for item in result.scalars()}


def _assemble(accruals: list[Accrual], today: date, securities_value: Decimal) -> CalendarOut:
    past_from = add_months(today, -12)
    future_to = add_months(today, 12)
    start = month_start(today)
    month_received: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    month_upcoming: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    received_12m = ZERO
    received_all_time = ZERO
    forecast_12m = ZERO
    events: list[CalendarEventOut] = []
    forecasts_as_of = None

    for item in accruals:
        if item.status != "received" and (forecasts_as_of is None or item.updated_at.date() > forecasts_as_of):
            forecasts_as_of = item.updated_at.date() if item.updated_at else today
        amount = item.amount_rub or ZERO
        if item.status == "received":
            received_all_time += amount
            if past_from < item.event_date <= today:
                received_12m += amount
        if item.status != "received" and today < item.event_date <= future_to:
            forecast_12m += amount
        key = (item.event_date.year, item.event_date.month)
        if item.status == "received":
            month_received[key] += amount
        else:
            month_upcoming[key] += amount
        visible = (
            item.status == "received" and past_from < item.event_date <= today
        ) or (item.status != "received" and today < item.event_date <= future_to)
        if not visible:
            continue
        events.append(
            CalendarEventOut(
                figi=item.figi,
                ticker=item.ticker or item.figi,
                name=item.name or item.figi,
                kind=item.kind,
                status=item.status,
                event_date=item.event_date,
                amount=money_str(item.amount),
                currency=item.currency,
                amount_rub=money_str(amount),
                quantity=money_str(item.quantity or ZERO) if item.quantity else "0.00",
            )
        )

    months: list[CalendarMonthOut] = []
    for offset in range(12):
        cursor = add_months(start, offset)
        key = (cursor.year, cursor.month)
        received = month_received[key]
        upcoming = month_upcoming[key]
        months.append(
            CalendarMonthOut(
                year=cursor.year,
                month=cursor.month,
                received=money_str(received),
                upcoming=money_str(upcoming),
                total=money_str(received + upcoming),
            )
        )

    events.sort(key=lambda item: (item.event_date, item.ticker))
    yield_percent = None
    if securities_value > 0 and forecast_12m != 0:
        yield_percent = money_str(forecast_12m / securities_value * Decimal("100"))

    return CalendarOut(
        received_12m=money_str(received_12m),
        received_all_time=money_str(received_all_time),
        forecast_12m=money_str(forecast_12m),
        securities_value=money_str(securities_value),
        yield_percent=yield_percent,
        forecasts_as_of=forecasts_as_of,
        months=months,
        events=events,
    )


def _month_last_day(value: date) -> date:
    return add_months(month_start(value), 1) - timedelta(days=1)


async def load_payment_history(
    session: AsyncSession,
    user: User,
    *,
    period: str = "all",
    year: int | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
    today: date | None = None,
) -> PaymentHistoryOut:
    today = today or moscow_today()
    empty = PaymentHistoryOut(period=period)
    connection = await get_connection(session, user.id)
    if connection is None:
        return empty

    result = await session.execute(
        select(Accrual).where(Accrual.connection_id == connection.id, Accrual.status == "received")
    )
    received = list(result.scalars())
    if not received:
        return empty

    years = sorted({item.event_date.year for item in received})
    first_day = min(item.event_date for item in received)
    start, end, granularity = resolve_history_window(
        period=period,
        year=year,
        from_day=from_day,
        to_day=to_day,
        today=today,
        first_day=first_day,
    )

    totals: dict[date, Decimal] = defaultdict(lambda: ZERO)
    window_total = ZERO
    for item in received:
        if item.event_date < start or item.event_date > end:
            continue
        amount = item.amount_rub or ZERO
        window_total += amount
        key = item.event_date if granularity == "day" else _month_last_day(item.event_date)
        totals[key] += amount

    points: list[PaymentHistoryPointOut] = []
    if granularity == "day":
        cursor = start
        while cursor <= end:
            points.append(PaymentHistoryPointOut(day=cursor, amount=money_str(totals[cursor])))
            cursor += timedelta(days=1)
    else:
        cursor = month_start(start)
        last = month_start(end)
        while cursor <= last:
            bucket = _month_last_day(cursor)
            points.append(PaymentHistoryPointOut(day=bucket, amount=money_str(totals[bucket])))
            cursor = add_months(cursor, 1)

    return PaymentHistoryOut(
        period=period,
        granularity=granularity,
        from_day=start,
        to_day=end,
        years=years,
        total=money_str(window_total),
        points=points,
    )
