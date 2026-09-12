"""daily prices and portfolio snapshots

Revision ID: 0006_history
Revises: 0005_accruals
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_history"
down_revision: Union[str, Sequence[str], None] = "0005_accruals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prices_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("figi", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="tinkoff"),
        sa.UniqueConstraint("figi", "day", name="uq_prices_daily_figi_day"),
    )
    op.create_index("ix_prices_daily_figi", "prices_daily", ["figi"])
    op.create_index("ix_prices_daily_day", "prices_daily", ["day"])

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("broker_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("value_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("cash_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("securities_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("invested_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("imoex_close", sa.Numeric(20, 8), nullable=True),
        sa.UniqueConstraint("connection_id", "day", name="uq_portfolio_snapshots_connection_day"),
    )
    op.create_index("ix_portfolio_snapshots_connection_id", "portfolio_snapshots", ["connection_id"])
    op.create_index("ix_portfolio_snapshots_day", "portfolio_snapshots", ["day"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_day", table_name="portfolio_snapshots")
    op.drop_index("ix_portfolio_snapshots_connection_id", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_index("ix_prices_daily_day", table_name="prices_daily")
    op.drop_index("ix_prices_daily_figi", table_name="prices_daily")
    op.drop_table("prices_daily")
