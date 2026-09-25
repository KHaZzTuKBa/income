from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )
    token_encrypted: Mapped[str] = mapped_column(Text)
    token_hint: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="idle")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    accounts: Mapped[list["Account"]] = relationship(back_populates="connection")
    sync_runs: Mapped[list["SyncRun"]] = relationship(back_populates="connection")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("broker_connections.id", ondelete="CASCADE"),
        index=True,
    )
    broker_account_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    type: Mapped[str] = mapped_column(String(32), default="broker")
    status: Mapped[str] = mapped_column(String(16), default="open")
    access_level: Mapped[str] = mapped_column(String(32), default="")

    connection: Mapped[BrokerConnection] = relationship(back_populates="accounts")
    operations: Mapped[list["Operation"]] = relationship(back_populates="account")
    positions: Mapped[list["Position"]] = relationship(back_populates="account")


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    figi: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    ticker: Mapped[str] = mapped_column(String(32), default="")
    isin: Mapped[str] = mapped_column(String(32), default="")
    name: Mapped[str] = mapped_column(String(256), default="")
    instrument_type: Mapped[str] = mapped_column(String(32), default="")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    lot: Mapped[int] = mapped_column(Integer, default=1)
    uid: Mapped[str] = mapped_column(String(64), default="")
    nominal: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    nominal_currency: Mapped[str] = mapped_column(String(8), default="")
    sector: Mapped[str] = mapped_column(String(64), default="")


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("account_id", "broker_operation_id", name="uq_operations_account_broker_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
    )
    broker_operation_id: Mapped[str] = mapped_column(String(64))
    parent_operation_id: Mapped[str] = mapped_column(String(64), default="")
    figi: Mapped[str] = mapped_column(String(32), default="")
    instrument_uid: Mapped[str] = mapped_column(String(64), default="")
    operation_type: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(256), default="")
    state: Mapped[str] = mapped_column(String(32), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    payment: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    commission: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    account: Mapped[Account] = relationship(back_populates="operations")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "figi", name="uq_positions_account_figi"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
    )
    figi: Mapped[str] = mapped_column(String(32), default="")
    instrument_uid: Mapped[str] = mapped_column(String(64), default="")
    instrument_type: Mapped[str] = mapped_column(String(32), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    average_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    average_price_currency: Mapped[str] = mapped_column(String(8), default="RUB")
    current_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    current_price_currency: Mapped[str] = mapped_column(String(8), default="RUB")

    account: Mapped[Account] = relationship(back_populates="positions")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("broker_connections.id", ondelete="CASCADE"),
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(16), default="manual")
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accounts_count: Mapped[int] = mapped_column(Integer, default=0)
    operations_count: Mapped[int] = mapped_column(Integer, default=0)
    instruments_count: Mapped[int] = mapped_column(Integer, default=0)
    positions_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    connection: Mapped[BrokerConnection] = relationship(back_populates="sync_runs")
