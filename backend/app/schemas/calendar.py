from datetime import date
from typing import Literal

from pydantic import BaseModel

PaymentGranularity = Literal["day", "month"]


class CalendarEventOut(BaseModel):
    figi: str
    ticker: str
    name: str
    kind: str
    status: str
    event_date: date
    amount: str
    currency: str
    amount_rub: str
    quantity: str


class CalendarMonthOut(BaseModel):
    year: int
    month: int
    received: str
    upcoming: str
    total: str


class CalendarOut(BaseModel):
    received_12m: str
    received_all_time: str
    forecast_12m: str
    securities_value: str
    yield_percent: str | None = None
    forecasts_as_of: date | None = None
    months: list[CalendarMonthOut]
    events: list[CalendarEventOut]


class PaymentHistoryPointOut(BaseModel):
    day: date
    amount: str


class PaymentHistoryOut(BaseModel):
    period: str = "all"
    granularity: PaymentGranularity = "month"
    from_day: date | None = None
    to_day: date | None = None
    years: list[int] = []
    total: str = "0.00"
    points: list[PaymentHistoryPointOut] = []
