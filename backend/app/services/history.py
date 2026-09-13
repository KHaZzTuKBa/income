from __future__ import annotations

import asyncio
import calendar
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
from app.models.history import AccountSnapshot, PortfolioSnapshot, PriceDaily
from app.schemas.history import HistoryGranularity, HistoryOut, HistoryPointOut, HistorySeriesOut
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
CUSTOM_DAY_MAX = 45
Holding = tuple[Decimal, Decimal, str]


def compute_snapshots(
    operations: list[Any],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    imoex: dict[date, Decimal],
    start: date,
    end: date,
    close_currency: dict[str, str] | None = None,
    figi_aliases: dict[str, str] | None = None,
    account_types: dict[int, str] | None = None,
) -> list[dict]:
    return compute_all_snapshots(
        operations,
        instruments,
        closes,
        imoex,
        start,
        end,
        close_currency=close_currency,
        figi_aliases=figi_aliases,
        account_types=account_types,
    )[None]


def compute_all_snapshots(
    operations: list[Any],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    imoex: dict[date, Decimal],
    start: date,
    end: date,
    close_currency: dict[str, str] | None = None,
    extra_account_ids: list[int] | None = None,
    figi_aliases: dict[str, str] | None = None,
    account_types: dict[int, str] | None = None,
) -> dict[int | None, list[dict]]:
    aliases = figi_aliases or canonical_figi_map(instruments)
    priced = merge_alias_prices(closes, aliases)
    types = account_types or {}
    ordered = sorted(
        [item for item in operations if _executed(item)],
        key=lambda item: (getattr(item, "occurred_at"), getattr(item, "id", 0) or 0),
    )
    account_ids = sorted(
        {
            int(getattr(item, "account_id", 0) or 0)
            for item in ordered
            if getattr(item, "account_id", None)
        }
        | {int(item) for item in extra_account_ids or [] if item}
    )
    price_ccy = close_currency or {}
    index = 0
    holdings: dict[tuple[int, str], Holding] = {}
    cash_pay: dict[tuple[int, str], Decimal] = defaultdict(lambda: ZERO)
    invested_by: dict[int, Decimal] = defaultdict(lambda: ZERO)
    series: dict[int | None, list[dict]] = {None: []}
    for account_id in account_ids:
        series[account_id] = []
    day = start
    while day <= end:
        while index < len(ordered) and moscow_day(ordered[index].occurred_at) <= day:
            account_id, invested = _apply_operation(
                ordered[index], holdings, cash_pay, priced, day, aliases
            )
            if account_id:
                invested_by[account_id] += invested
            index += 1
        fx_prices = _fx_prices(priced, day)
        total_cash = ZERO
        total_sec = ZERO
        total_invested = ZERO
        for account_id in account_ids:
            cash = _cash_rub(
                cash_pay,
                holdings,
                instruments,
                fx_prices,
                account_id,
                include_payments=types.get(account_id) != "invest_box",
            )
            securities = _securities_rub(
                holdings, instruments, priced, price_ccy, day, fx_prices, account_id
            )
            invested = invested_by[account_id]
            series[account_id].append(
                {
                    "day": day,
                    "value": cash + securities,
                    "cash": cash,
                    "securities": securities,
                    "invested": invested,
                    "imoex": None,
                }
            )
            total_cash += cash
            total_sec += securities
            total_invested += invested
        series[None].append(
            {
                "day": day,
                "value": total_cash + total_sec,
                "cash": total_cash,
                "securities": total_sec,
                "invested": total_invested,
                "imoex": imoex.get(day),
            }
        )
        day += timedelta(days=1)
    return series


def instrument_group_key(instrument: Any | None, figi: str) -> str:
    """Один ключ для сменённых FIGI одной бумаги (тот же ISIN и тикер). TMON@ отдельно от TMON."""
    if instrument is not None and _is_cash_figi(figi, instrument):
        return f"figi:{figi}"
    isin = (getattr(instrument, "isin", None) or "").strip().upper()
    ticker = (getattr(instrument, "ticker", None) or "").strip().upper()
    if isin and ticker:
        return f"{isin}:{ticker}"
    if isin:
        return f"isin:{isin}"
    if ticker:
        return f"ticker:{ticker}"
    return f"figi:{figi}"


def canonical_figi_map(
    instruments: dict[str, Any],
    preferred: set[str] | None = None,
    price_counts: dict[str, int] | None = None,
) -> dict[str, str]:
    preferred = preferred or set()
    price_counts = price_counts or {}
    groups: dict[str, list[str]] = defaultdict(list)
    for figi, instrument in instruments.items():
        if not figi:
            continue
        groups[instrument_group_key(instrument, figi)].append(figi)
    mapping: dict[str, str] = {}
    for figis in groups.values():
        chosen = _choose_canonical_figi(figis, preferred, price_counts)
        for figi in figis:
            mapping[figi] = chosen
    return mapping


def _choose_canonical_figi(
    figis: list[str], preferred: set[str], price_counts: dict[str, int]
) -> str:
    for figi in figis:
        if figi in preferred:
            return figi
    return max(figis, key=lambda item: (price_counts.get(item, 0), item))


def merge_alias_prices(
    closes: dict[str, dict[date, Decimal]], aliases: dict[str, str]
) -> dict[str, dict[date, Decimal]]:
    if not aliases:
        return closes
    groups: dict[str, set[str]] = defaultdict(set)
    for figi, canonical in aliases.items():
        groups[canonical].add(figi)
        groups[canonical].add(canonical)
    merged = {figi: dict(series) for figi, series in closes.items()}
    for canonical, members in groups.items():
        combined: dict[date, Decimal] = {}
        for figi in members:
            if figi != canonical:
                combined.update(merged.get(figi, {}))
        combined.update(merged.get(canonical, {}))
        if not combined:
            continue
        for figi in members:
            merged[figi] = dict(combined)
    return merged


def opening_balances(rows: list[Any], start: date) -> tuple[Decimal, Decimal]:
    """Снимок на день до начала окна: от него считаются вводы и прибыль за период."""
    previous = None
    for item in rows:
        day = getattr(item, "day", None)
        if day is None:
            day = item["day"]
        if day < start:
            previous = item
        else:
            break
    if previous is None:
        return ZERO, ZERO
    if hasattr(previous, "value_rub"):
        return Decimal(str(previous.value_rub)), Decimal(str(previous.invested_rub))
    return Decimal(str(previous["value"])), Decimal(str(previous["invested"]))


def period_invested_and_profit(
    open_value: Decimal,
    open_invested: Decimal,
    value: Decimal,
    invested: Decimal,
) -> tuple[Decimal, Decimal]:
    """Чистые вводы за окно и прибыль: изменение (стоимость − вложено)."""
    invested_delta = invested - open_invested
    profit = (value - invested) - (open_value - open_invested)
    return invested_delta, profit


def aggregate_points(points: list[dict], granularity: HistoryGranularity) -> list[dict]:
    """Месячная точка — стоимость на последний день месяца, не сумма дней."""
    if granularity == "day" or not points:
        return points
    buckets: dict[tuple[int, int], dict] = {}
    order: list[tuple[int, int]] = []
    for item in points:
        day: date = item["day"]
        key = (day.year, day.month)
        if key not in buckets:
            order.append(key)
        buckets[key] = item
    return [buckets[key] for key in order]


def resolve_history_window(
    *,
    period: str,
    year: int | None,
    from_day: date | None,
    to_day: date | None,
    today: date,
    first_day: date | None,
) -> tuple[date, date, HistoryGranularity]:
    if period == "custom" and from_day and to_day:
        start, end = (from_day, to_day) if from_day <= to_day else (to_day, from_day)
        granularity: HistoryGranularity = "day" if (end - start).days <= CUSTOM_DAY_MAX else "month"
        return start, end, granularity
    if period == "week":
        return today - timedelta(days=6), today, "day"
    if period == "month":
        return today - timedelta(days=29), today, "day"
    if period == "year":
        selected = year or today.year
        return date(selected, 1, 1), min(date(selected, 12, 31), today), "month"
    if period == "6m":
        return shift_months(today, -6), today, "month"
    if period == "1y":
        return shift_months(today, -12), today, "month"
    start = first_day or today
    return start, today, "month"


def shift_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


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
            accounts_ready = await account_snapshots_exist(session, connection.id)
            if last == today and accounts_ready:
                return
        await _rebuild(session, connection, today)


async def load_history(
    session: AsyncSession,
    connection: BrokerConnection | None,
    *,
    period: str = "all",
    year: int | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
) -> HistoryOut:
    empty = HistoryOut(
        building=False,
        period=period,
        points=[],
        series=[],
        xirr_percent=None,
        xirr_from=None,
    )
    if connection is None:
        return empty
    accounts_result = await session.execute(
        select(Account).where(Account.connection_id == connection.id).order_by(Account.id)
    )
    accounts = list(accounts_result.scalars())
    names = {item.id: (item.name or item.broker_account_id) for item in accounts}

    total_rows = list(
        (
            await session.execute(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.connection_id == connection.id)
                .order_by(PortfolioSnapshot.day)
            )
        ).scalars()
    )
    account_rows: dict[int, list[AccountSnapshot]] = {item.id: [] for item in accounts}
    if accounts:
        acc_result = await session.execute(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id.in_([item.id for item in accounts]))
            .order_by(AccountSnapshot.day)
        )
        for row in acc_result.scalars():
            account_rows.setdefault(row.account_id, []).append(row)

    years = sorted({row.day.year for row in total_rows})
    first_day = total_rows[0].day if total_rows else None
    last_day = total_rows[-1].day if total_rows else None
    start, end, granularity = resolve_history_window(
        period=period,
        year=year,
        from_day=from_day,
        to_day=to_day,
        today=moscow_today(),
        first_day=first_day,
    )
    building = last_day is None

    def to_points(rows: list, with_imoex: bool) -> list[HistoryPointOut]:
        daily = [
            {
                "day": item.day,
                "value": item.value_rub,
                "cash": item.cash_rub,
                "securities": item.securities_rub,
                "invested": item.invested_rub,
                "imoex": item.imoex_close if with_imoex else None,
            }
            for item in rows
            if start <= item.day <= end
        ]
        return [_point_out(item, with_imoex) for item in aggregate_points(daily, granularity)]

    points = to_points(total_rows, True)
    total_open_value, total_open_invested = opening_balances(total_rows, start)
    account_series: list[HistorySeriesOut] = []
    for account in accounts:
        open_value, open_invested = opening_balances(account_rows.get(account.id, []), start)
        account_series.append(
            HistorySeriesOut(
                account_id=account.id,
                account_name=names.get(account.id, account.broker_account_id),
                points=to_points(account_rows.get(account.id, []), False),
                open_value=money_str(open_value),
                open_invested=money_str(open_invested),
            )
        )
    series = [
        HistorySeriesOut(
            account_id=None,
            account_name="Все счета",
            points=points,
            open_value=money_str(total_open_value),
            open_invested=money_str(total_open_invested),
        ),
        *account_series,
    ]
    return HistoryOut(
        building=building,
        period=period,
        granularity=granularity,
        from_day=start if total_rows else None,
        to_day=end if total_rows else None,
        years=years,
        points=points,
        series=series,
        xirr_percent=None,
        xirr_from=None,
    )


def _point_out(item: dict, with_imoex: bool) -> HistoryPointOut:
    imoex = item.get("imoex") if with_imoex else None
    return HistoryPointOut(
        day=item["day"],
        value=money_str(item["value"]),
        cash=money_str(item["cash"]),
        securities=money_str(item["securities"]),
        invested=money_str(item["invested"]),
        imoex=money_str(imoex) if imoex is not None else None,
    )


async def account_snapshots_exist(session: AsyncSession, connection_id: int) -> bool:
    account_ids = select(Account.id).where(Account.connection_id == connection_id)
    count = await session.scalar(
        select(func.count()).select_from(AccountSnapshot).where(AccountSnapshot.account_id.in_(account_ids))
    )
    return int(count or 0) > 0


async def _rebuild(session: AsyncSession, connection: BrokerConnection, today: date) -> None:
    ops_result = await session.execute(
        select(Operation)
        .join(Account)
        .where(Account.connection_id == connection.id)
        .order_by(Operation.occurred_at, Operation.id)
    )
    operations = list(ops_result.scalars())
    account_ids = list(
        (
            await session.execute(select(Account.id).where(Account.connection_id == connection.id))
        ).scalars()
    )
    account_types = {
        item.id: item.type
        for item in (
            await session.execute(select(Account).where(Account.connection_id == connection.id))
        ).scalars()
    }
    if not operations:
        await _clear_snapshots(session, connection.id, account_ids)
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
    instruments = await _expand_instruments_by_isin(session, instruments)
    preferred_figis = {item.figi for item in positions if item.figi}
    figi_aliases = canonical_figi_map(instruments, preferred=preferred_figis)
    source_figis = {item.figi for item in operations if item.figi}
    source_figis.update(item.figi for item in positions if item.figi)
    related = set(source_figis)
    needed_canonical = {figi_aliases.get(figi, figi) for figi in source_figis}
    for figi, canon in figi_aliases.items():
        if canon in needed_canonical:
            related.add(figi)
            related.add(canon)
    related.update(figi for code, figi in CURRENCY_FIGI.items() if code != "RUB")
    candle_figis = [
        figi
        for figi in related
        if figi and figi != IMOEX and not _is_cash_figi(figi, instruments.get(figi))
    ]
    fx_figis = [figi for code, figi in CURRENCY_FIGI.items() if code != "RUB"]
    candle_figis = list(dict.fromkeys([*candle_figis, *fx_figis]))

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

    stored, close_currency = await _load_prices(session, [*candle_figis, IMOEX], start, today)
    if not fetched_any and not stored:
        await _snapshot_today_only(session, connection, positions, instruments, today, account_ids)
        return

    figi_aliases = canonical_figi_map(
        instruments,
        preferred=preferred_figis,
        price_counts={figi: len(series) for figi, series in stored.items()},
    )
    closes = {figi: _ffill(series, start, today) for figi, series in stored.items() if figi != IMOEX}
    imoex = _ffill(stored.get(IMOEX, {}), start, today)
    series = compute_all_snapshots(
        operations,
        instruments,
        closes,
        imoex,
        start,
        today,
        close_currency=close_currency,
        extra_account_ids=account_ids,
        figi_aliases=figi_aliases,
        account_types=account_types,
    )
    _pin_last(series, positions, instruments, closes, today)

    await _clear_snapshots(session, connection.id, account_ids)
    for item in series.get(None, []):
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
    for account_id, rows in series.items():
        if account_id is None:
            continue
        for item in rows:
            session.add(
                AccountSnapshot(
                    account_id=account_id,
                    day=item["day"],
                    value_rub=item["value"],
                    cash_rub=item["cash"],
                    securities_rub=item["securities"],
                    invested_rub=item["invested"],
                )
            )
    await session.commit()
    logger.info("History rebuilt id=%s days=%s accounts=%s", connection.id, len(series.get(None, [])), len(account_ids))


async def _clear_snapshots(session: AsyncSession, connection_id: int, account_ids: list[int]) -> None:
    await session.execute(delete(PortfolioSnapshot).where(PortfolioSnapshot.connection_id == connection_id))
    if account_ids:
        await session.execute(delete(AccountSnapshot).where(AccountSnapshot.account_id.in_(account_ids)))


async def _snapshot_today_only(
    session: AsyncSession,
    connection: BrokerConnection,
    positions: list[Position],
    instruments: dict[str, Instrument],
    today: date,
    account_ids: list[int],
) -> None:
    pin = _today_totals(positions, instruments, {}, today)
    await _clear_snapshots(session, connection.id, account_ids)
    if pin is not None:
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
    by_account: dict[int, list[Position]] = defaultdict(list)
    for item in positions:
        by_account[item.account_id].append(item)
    for account_id in account_ids:
        acc_pin = _today_totals(by_account.get(account_id, []), instruments, {}, today)
        if acc_pin is None:
            acc_pin = (ZERO, ZERO, ZERO)
        session.add(
            AccountSnapshot(
                account_id=account_id,
                day=today,
                value_rub=acc_pin[0],
                cash_rub=acc_pin[1],
                securities_rub=acc_pin[2],
                invested_rub=ZERO,
            )
        )
    await session.commit()


def _pin_last(
    series: dict[int | None, list[dict]],
    positions: list[Position],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    today: date,
) -> None:
    pin = _today_totals(positions, instruments, closes, today)
    total_rows = series.get(None) or []
    if pin is not None and total_rows:
        total_rows[-1]["value"] = pin[0]
        total_rows[-1]["cash"] = pin[1]
        total_rows[-1]["securities"] = pin[2]
    by_account: dict[int, list[Position]] = defaultdict(list)
    for item in positions:
        by_account[item.account_id].append(item)
    for account_id, rows in series.items():
        if account_id is None or not rows:
            continue
        acc_pin = _today_totals(by_account.get(account_id, []), instruments, closes, today)
        if acc_pin is None:
            continue
        rows[-1]["value"] = acc_pin[0]
        rows[-1]["cash"] = acc_pin[1]
        rows[-1]["securities"] = acc_pin[2]


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
    holdings: dict[tuple[int, str], Holding],
    cash_pay: dict[tuple[int, str], Decimal],
    closes: dict[str, dict[date, Decimal]],
    day: date,
    aliases: dict[str, str] | None = None,
) -> tuple[int, Decimal]:
    currency = (getattr(operation, "currency", None) or "RUB").upper()
    account_id = int(getattr(operation, "account_id", 0) or 0)
    payment = Decimal(str(getattr(operation, "payment", 0) or 0))
    commission = Decimal(str(getattr(operation, "commission", 0) or 0))
    cash_pay[(account_id, currency)] += payment + commission
    invested = ZERO
    if (getattr(operation, "operation_type", "") or "") in CASHFLOW_TYPES:
        invested = to_rub(payment, currency, _fx_prices(closes, day))

    figi = getattr(operation, "figi", "") or ""
    if figi:
        figi = (aliases or {}).get(str(figi), str(figi))
    op_type = getattr(operation, "operation_type", "") or ""
    if figi and op_type in BUY_TYPES | SELL_TYPES:
        key = (account_id, str(figi))
        qty, avg, avg_ccy = holdings.get(key, (ZERO, ZERO, currency))
        add_qty = Decimal(str(getattr(operation, "quantity", 0) or 0))
        if op_type in BUY_TYPES and add_qty > 0:
            price = Decimal(str(getattr(operation, "price", 0) or 0))
            if price == 0:
                price = abs(payment) / add_qty if add_qty else ZERO
            new_qty = qty + add_qty
            avg = (qty * avg + add_qty * price) / new_qty if new_qty else ZERO
            holdings[key] = (new_qty, avg, currency or avg_ccy)
        elif op_type in SELL_TYPES:
            qty = qty - add_qty
            holdings[key] = (ZERO, ZERO, avg_ccy) if qty <= QTY_EPS else (qty, avg, avg_ccy)
    return account_id, invested


def _cash_rub(
    cash_pay: dict[tuple[int, str], Decimal],
    holdings: dict[tuple[int, str], Holding],
    instruments: dict[str, Instrument],
    fx_prices: dict[str, Decimal],
    account_id: int | None = None,
    include_payments: bool = True,
) -> Decimal:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    if include_payments:
        for (acc, currency), amount in cash_pay.items():
            if account_id is not None and acc != account_id:
                continue
            totals[currency.upper()] += amount
    for (acc, figi), (qty, _avg, _ccy) in holdings.items():
        if account_id is not None and acc != account_id:
            continue
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
    holdings: dict[tuple[int, str], Holding],
    instruments: dict[str, Instrument],
    closes: dict[str, dict[date, Decimal]],
    close_currency: dict[str, str],
    day: date,
    fx_prices: dict[str, Decimal],
    account_id: int | None = None,
) -> Decimal:
    by_figi: dict[str, tuple[Decimal, Decimal, str]] = {}
    for (acc, figi), (qty, avg, avg_ccy) in holdings.items():
        if account_id is not None and acc != account_id:
            continue
        if qty <= 0 or _is_cash_figi(figi, instruments.get(figi)):
            continue
        prev_qty, prev_avg, prev_ccy = by_figi.get(figi, (ZERO, ZERO, avg_ccy))
        new_qty = prev_qty + qty
        avg_price = (prev_qty * prev_avg + qty * avg) / new_qty if new_qty else ZERO
        by_figi[figi] = (new_qty, avg_price, avg_ccy or prev_ccy)

    total = ZERO
    for figi, (qty, avg, avg_ccy) in by_figi.items():
        instrument = instruments.get(figi)
        instrument_type = instrument.instrument_type if instrument else ""
        raw, currency = _quote_for_day(
            figi, avg, avg_ccy, instrument, closes, close_currency, day
        )
        stored_nominal = instrument.nominal if instrument else ZERO
        stored_ccy = (instrument.nominal_currency if instrument else "") or ""
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


def _quote_for_day(
    figi: str,
    avg: Decimal,
    avg_ccy: str,
    instrument: Instrument | None,
    closes: dict[str, dict[date, Decimal]],
    close_currency: dict[str, str],
    day: date,
) -> tuple[Decimal, str]:
    series = closes.get(figi) or {}
    raw = series.get(day, ZERO)
    trade_ccy = (avg_ccy or "RUB").upper()
    inst_ccy = (
        close_currency.get(figi) or (instrument.currency if instrument else "") or "RUB"
    ).upper()
    if raw <= 0:
        return (avg, trade_ccy) if avg > 0 else (ZERO, inst_ccy)
    if avg <= 0 or trade_ccy == inst_ccy:
        return raw, inst_ccy
    ratio = raw / avg
    if Decimal("0.25") <= ratio <= Decimal("4"):
        return raw, trade_ccy
    return raw, inst_ccy


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
) -> tuple[dict[str, dict[date, Decimal]], dict[str, str]]:
    unique = [item for item in dict.fromkeys(figis) if item]
    if not unique:
        return {}, {}
    result = await session.execute(
        select(PriceDaily).where(
            PriceDaily.figi.in_(unique),
            PriceDaily.day >= start,
            PriceDaily.day <= end,
        )
    )
    stored: dict[str, dict[date, Decimal]] = defaultdict(dict)
    currencies: dict[str, str] = {}
    for item in result.scalars():
        stored[item.figi][item.day] = item.close
        if item.currency:
            currencies[item.figi] = item.currency
    return stored, currencies


async def _instruments_by_figi(session: AsyncSession, figis: list[str]) -> dict[str, Instrument]:
    unique = list({item for item in figis if item})
    if not unique:
        return {}
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(unique)))
    return {item.figi: item for item in result.scalars()}


async def _expand_instruments_by_isin(
    session: AsyncSession, instruments: dict[str, Instrument]
) -> dict[str, Instrument]:
    isins = [item.isin for item in instruments.values() if getattr(item, "isin", None)]
    if not isins:
        return instruments
    result = await session.execute(select(Instrument).where(Instrument.isin.in_(isins)))
    merged = dict(instruments)
    for item in result.scalars():
        merged[item.figi] = item
    return merged


def should_rebuild_in_request() -> bool:
    return not os.environ.get("PYTEST_CURRENT_TEST")
