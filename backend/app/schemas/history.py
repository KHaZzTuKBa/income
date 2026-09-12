from datetime import date

from pydantic import BaseModel


class HistoryPointOut(BaseModel):
    day: date
    value: str
    cash: str
    securities: str
    invested: str
    imoex: str | None = None


class HistoryOut(BaseModel):
    building: bool = False
    points: list[HistoryPointOut]
    xirr_percent: str | None = None
    xirr_from: date | None = None
