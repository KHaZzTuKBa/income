"""tinkoff sync tables

Revision ID: 0002_tinkoff_sync
Revises: 0001_create_users
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tinkoff_sync"
down_revision: Union[str, Sequence[str], None] = "0001_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="idle"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("history_from", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_broker_connections_user_id", "broker_connections", ["user_id"], unique=True)

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("broker_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker_account_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="broker"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("access_level", sa.String(length=32), nullable=False, server_default=""),
    )
    op.create_index("ix_accounts_connection_id", "accounts", ["connection_id"])
    op.create_index("ix_accounts_broker_account_id", "accounts", ["broker_account_id"], unique=True)

    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("figi", sa.String(length=32), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("isin", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("instrument_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("lot", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uid", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_instruments_figi", "instruments", ["figi"], unique=True)

    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker_operation_id", sa.String(length=64), nullable=False),
        sa.Column("parent_operation_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("figi", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("instrument_uid", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("operation_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("payment", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("commission", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "broker_operation_id", name="uq_operations_account_broker_id"),
    )
    op.create_index("ix_operations_account_id", "operations", ["account_id"])
    op.create_index("ix_operations_occurred_at", "operations", ["occurred_at"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("figi", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("instrument_uid", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("instrument_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("average_price", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("average_price_currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("current_price", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("current_price_currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.UniqueConstraint("account_id", "figi", name="uq_positions_account_figi"),
    )
    op.create_index("ix_positions_account_id", "positions", ["account_id"])

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("broker_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accounts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("operations_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("instruments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_sync_runs_connection_id", "sync_runs", ["connection_id"])


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_table("positions")
    op.drop_table("operations")
    op.drop_table("instruments")
    op.drop_table("accounts")
    op.drop_table("broker_connections")
