from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def money_to_decimal(value: object | None) -> Decimal:
    if value is None:
        return Decimal("0")
    units = getattr(value, "units", 0) or 0
    nano = getattr(value, "nano", 0) or 0
    return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)


def enum_name(value: object | None) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value)


def to_utc(value: object | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    to_datetime = getattr(value, "ToDatetime", None)
    if callable(to_datetime):
        converted = to_datetime()
        if converted.tzinfo is None:
            return converted.replace(tzinfo=timezone.utc)
        return converted.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


ACCOUNT_TYPE_MAP = {
    "ACCOUNT_TYPE_TINKOFF": "broker",
    "ACCOUNT_TYPE_TINKOFF_IIS": "iis",
    "ACCOUNT_TYPE_INVEST_BOX": "invest_box",
    "ACCOUNT_TYPE_INVEST_FUND": "invest_fund",
}

ACCOUNT_STATUS_MAP = {
    "ACCOUNT_STATUS_OPEN": "open",
    "ACCOUNT_STATUS_CLOSED": "closed",
    "ACCOUNT_STATUS_NEW": "new",
}

BUY_TYPES = {
    "OPERATION_TYPE_BUY",
    "OPERATION_TYPE_BUY_CARD",
    "OPERATION_TYPE_BUY_MARGIN",
    "OPERATION_TYPE_INPUT_SECURITIES",
    "OPERATION_TYPE_DELIVERY_BUY",
}

SELL_TYPES = {
    "OPERATION_TYPE_SELL",
    "OPERATION_TYPE_SELL_CARD",
    "OPERATION_TYPE_SELL_MARGIN",
    "OPERATION_TYPE_OUTPUT_SECURITIES",
    "OPERATION_TYPE_DELIVERY_SELL",
}


@dataclass
class AccountDTO:
    broker_account_id: str
    name: str
    type: str
    status: str
    access_level: str


@dataclass
class OperationDTO:
    broker_account_id: str
    broker_operation_id: str
    parent_operation_id: str
    figi: str
    instrument_uid: str
    operation_type: str
    name: str
    state: str
    quantity: Decimal
    price: Decimal
    payment: Decimal
    commission: Decimal
    currency: str
    occurred_at: datetime


@dataclass
class PositionDTO:
    broker_account_id: str
    figi: str
    instrument_uid: str
    instrument_type: str
    quantity: Decimal
    average_price: Decimal
    average_price_currency: str
    current_price: Decimal
    current_price_currency: str
    source: str = "portfolio"


@dataclass
class InstrumentDTO:
    figi: str
    ticker: str = ""
    isin: str = ""
    name: str = ""
    instrument_type: str = ""
    currency: str = "RUB"
    lot: int = 1
    uid: str = ""


@dataclass
class InvestPayload:
    accounts: list[AccountDTO] = field(default_factory=list)
    operations: list[OperationDTO] = field(default_factory=list)
    positions: list[PositionDTO] = field(default_factory=list)
    instruments: list[InstrumentDTO] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class InvestClientError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
