from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


class ConnectionOut(BaseModel):
    configured: bool
    token_hint: str | None = None
    status: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    history_from: date | None = None
    accounts_count: int = 0
    operations_count: int = 0
    positions_count: int = 0


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    accounts_count: int
    operations_count: int
    instruments_count: int
    positions_count: int
    error_message: str | None
    notes: str | None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker_account_id: str
    name: str
    type: str
    status: str


class PositionOut(BaseModel):
    account_id: int
    account_name: str
    figi: str
    ticker: str
    name: str
    instrument_type: str
    quantity: str
    average_price: str
    average_price_currency: str
    current_price: str
    current_price_currency: str


class OperationOut(BaseModel):
    id: int
    account_name: str
    broker_operation_id: str
    operation_type: str
    name: str
    figi: str
    ticker: str
    quantity: str
    payment: str
    currency: str
    occurred_at: datetime
