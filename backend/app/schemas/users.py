from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UserStatus = Literal["pending", "active", "frozen", "rejected"]
UserAction = Literal["approve", "reject", "freeze", "unfreeze", "delete"]


class RegisterIn(BaseModel):
    username: str = Field(max_length=256)
    email: str = Field(max_length=512)
    phone: str = Field(max_length=64)
    password: str = Field(max_length=256)


class RegisterOut(BaseModel):
    status: UserStatus


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    phone: str | None
    status: UserStatus
    created_at: datetime
    reviewed_at: datetime | None
    has_portfolio: bool = False


class AdminUsersOut(BaseModel):
    items: list[AdminUserOut]
    counts: dict[str, int]


class BulkActionIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    action: UserAction


class BulkActionOut(BaseModel):
    updated: int
    skipped: int


class LegacyPortfolioOut(BaseModel):
    has_portfolio: bool
    token_hint: str | None = None
    accounts_count: int = 0
    categories_count: int = 0


class TransferIn(BaseModel):
    user_id: int
