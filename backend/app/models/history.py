from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PriceDaily(Base):
    __tablename__ = "prices_daily"
    __table_args__ = (UniqueConstraint("figi", "day", name="uq_prices_daily_figi_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    figi: Mapped[str] = mapped_column(String(32), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    source: Mapped[str] = mapped_column(String(16), default="tinkoff")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("connection_id", "day", name="uq_portfolio_snapshots_connection_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("broker_connections.id", ondelete="CASCADE"),
        index=True,
    )
    day: Mapped[date] = mapped_column(Date, index=True)
    value_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    cash_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    securities_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    invested_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    imoex_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "day", name="uq_account_snapshots_account_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
    )
    day: Mapped[date] = mapped_column(Date, index=True)
    value_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    cash_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    securities_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    invested_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
