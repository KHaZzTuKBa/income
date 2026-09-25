from pydantic import BaseModel


class SectorPaperOut(BaseModel):
    figi: str
    ticker: str
    name: str
    value: str
    share: str


class SectorSliceOut(BaseModel):
    key: str
    label: str
    value: str
    share: str
    holdings_count: int
    holdings: list[SectorPaperOut] = []


class SectorPieOut(BaseModel):
    key: str
    account_id: int | None = None
    label: str
    total: str
    slices: list[SectorSliceOut]


class SectorHoldingOut(BaseModel):
    figi: str
    ticker: str
    name: str
    sector: str
    sector_label: str
    value: str


class SectorsOut(BaseModel):
    pies: list[SectorPieOut]
    holdings: list[SectorHoldingOut]
