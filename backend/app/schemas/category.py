from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None
    target_share: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: int | None = None
    target_share: Decimal | None = Field(default=None, ge=0, le=100)
    sort_order: int | None = None


class AssignmentIn(BaseModel):
    figi: str = Field(min_length=1, max_length=32)
    category_id: int | None = None


class CategoryHoldingOut(BaseModel):
    figi: str
    ticker: str
    name: str
    value: str
    is_cash: bool


class CategoryNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str
    target_share: str
    sort_order: int
    value: str
    own_value: str
    fact_share: str
    delta_share: str
    holdings: list[CategoryHoldingOut]
    children: list["CategoryNodeOut"]


CategoryNodeOut.model_rebuild()


class CategoriesOut(BaseModel):
    tree: list[CategoryNodeOut]
    unassigned: list[CategoryHoldingOut]
    portfolio_value: str
    root_target: str
    unassigned_value: str
    unassigned_share: str
