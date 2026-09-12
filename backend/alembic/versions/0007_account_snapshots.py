"""per-account daily snapshots

Revision ID: 0007_account_snapshots
Revises: 0006_history
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_account_snapshots"
down_revision: Union[str, Sequence[str], None] = "0006_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("value_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("cash_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("securities_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("invested_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.UniqueConstraint("account_id", "day", name="uq_account_snapshots_account_day"),
    )
    op.create_index("ix_account_snapshots_account_id", "account_snapshots", ["account_id"])
    op.create_index("ix_account_snapshots_day", "account_snapshots", ["day"])


def downgrade() -> None:
    op.drop_index("ix_account_snapshots_day", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_account_id", table_name="account_snapshots")
    op.drop_table("account_snapshots")
