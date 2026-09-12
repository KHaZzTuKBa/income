from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Accrual(Base):
    __tablename__ = "accruals"
    __table_args__ = (
        UniqueConstraint("connection_id", "source_key", name="uq_accruals_connection_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("broker_connections.id", ondelete="CASCADE"),
        index=True,
    )
    figi: Mapped[str] = mapped_column(String(32), default="", index=True)
    kind: Mapped[str] = mapped_column(String(16), default="dividend")
    status: Mapped[str] = mapped_column(String(16), default="received")
    event_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(16), default="operations")
    source_key: Mapped[str] = mapped_column(String(128))
    ticker: Mapped[str] = mapped_column(String(32), default="")
    name: Mapped[str] = mapped_column(String(256), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
