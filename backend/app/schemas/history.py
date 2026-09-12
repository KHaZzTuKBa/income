from datetime import date
from typing import Literal

from pydantic import BaseModel

HistoryPeriod = Literal["week", "month", "year", "6m", "1y", "all", "custom"]
HistoryGranularity = Literal["day", "month"]


class HistoryPointOut(BaseModel):
    day: date
    value: str
    cash: str
    securities: str
    invested: str
    imoex: str | None = None


class HistorySeriesOut(BaseModel):
    account_id: int | None = None
    account_name: str
    points: list[HistoryPointOut]


class HistoryOut(BaseModel):
    building: bool = False
    period: str = "all"
    granularity: HistoryGranularity = "day"
    from_day: date | None = None
    to_day: date | None = None
    years: list[int] = []
    points: list[HistoryPointOut]
    series: list[HistorySeriesOut] = []
    xirr_percent: str | None = None
    xirr_from: date | None = None
