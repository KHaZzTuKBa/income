from datetime import date

from pydantic import BaseModel


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
    forecast_12m: str
    securities_value: str
    yield_percent: str | None = None
    forecasts_as_of: date | None = None
    months: list[CalendarMonthOut]
    events: list[CalendarEventOut]
