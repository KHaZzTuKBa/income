from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    target_share: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parent: Mapped["Category | None"] = relationship(
        back_populates="children",
        remote_side="Category.id",
    )
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    holdings: Mapped[list["HoldingCategory"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class HoldingCategory(Base):
    __tablename__ = "holdings_categories"
    __table_args__ = (UniqueConstraint("figi", name="uq_holdings_categories_figi"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        index=True,
    )
    figi: Mapped[str] = mapped_column(String(32), index=True)

    category: Mapped[Category] = relationship(back_populates="holdings")
