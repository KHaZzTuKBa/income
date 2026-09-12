from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.services.invest_types import CASHFLOW_TYPES

GUESSES = (0.1, 0.0, -0.1, 0.25, -0.25, 0.5, -0.5, 1.0, -0.9, 2.0)
MOSCOW = ZoneInfo("Europe/Moscow")

ToRub = Callable[[Decimal, str, dict[str, Decimal]], Decimal]


def moscow_today() -> date:
    return datetime.now(MOSCOW).date()


def moscow_day(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW).date()


def investor_cashflows(
    operations: list[Any],
    prices: dict[str, Decimal],
    today: date,
    value: Decimal,
    to_rub: ToRub,
) -> list[tuple[date, Decimal]]:
    flows: list[tuple[date, Decimal]] = []
    for operation in operations:
        state = (getattr(operation, "state", "") or "").upper()
        if state and "EXECUTED" not in state:
            continue
        if (getattr(operation, "operation_type", "") or "") not in CASHFLOW_TYPES:
            continue
        payment = Decimal(str(getattr(operation, "payment", 0) or 0))
        if payment == 0:
            continue
        currency = getattr(operation, "currency", None) or "RUB"
        occurred = getattr(operation, "occurred_at", None)
        if occurred is None:
            continue
        flows.append((moscow_day(occurred), -to_rub(payment, currency, prices)))
    if value != 0 or flows:
        flows.append((today, value))
    return flows


def xirr_percent(
    operations: list[Any],
    prices: dict[str, Decimal],
    today: date,
    value: Decimal,
    to_rub: ToRub,
) -> Decimal | None:
    rate = xirr(investor_cashflows(operations, prices, today, value, to_rub))
    if rate is None:
        return None
    return rate * Decimal("100")


def xirr(cashflows: list[tuple[date, Decimal]]) -> Decimal | None:
    """Годовая доходность (доля, не проценты) по потокам с датами. Как Excel XIRR."""
    by_day: dict[date, float] = {}
    for day, amount in cashflows:
        value = float(amount)
        if value == 0:
            continue
        by_day[day] = by_day.get(day, 0.0) + value
    items = sorted(by_day.items())
    if len(items) < 2:
        return None
    if not any(amount < 0 for _, amount in items) or not any(amount > 0 for _, amount in items):
        return None

    start = items[0][0]

    def years(day: date) -> float:
        return (day - start).days / 365.0

    def npv(rate: float) -> float:
        return sum(amount / (1.0 + rate) ** years(day) for day, amount in items)

    def dnpv(rate: float) -> float:
        return sum(
            -years(day) * amount / (1.0 + rate) ** (years(day) + 1.0) for day, amount in items
        )

    best: float | None = None
    best_abs = float("inf")
    for guess in GUESSES:
        rate = guess
        converged = False
        for _ in range(80):
            if rate <= -0.999999:
                rate = -0.999999
            value = npv(rate)
            deriv = dnpv(rate)
            abs_value = abs(value)
            if abs_value < best_abs:
                best_abs = abs_value
                best = rate
            if abs_value < 1e-8:
                converged = True
                best = rate
                break
            if abs(deriv) < 1e-14:
                break
            nxt = rate - value / deriv
            if nxt <= -0.999999:
                nxt = (rate - 0.999999) / 2.0
            if abs(nxt - rate) < 1e-10:
                rate = nxt
                converged = abs(npv(rate)) < 1e-5
                break
            rate = nxt
        if converged:
            return Decimal(str(round(rate, 8)))

    if best is None or best_abs > 1.0:
        return None
    return Decimal(str(round(best, 8)))
