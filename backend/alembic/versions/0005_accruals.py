"""dividend and coupon accruals

Revision ID: 0005_accruals
Revises: 0004_categories
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_accruals"
down_revision: Union[str, Sequence[str], None] = "0004_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accruals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("broker_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("figi", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="dividend"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="received"),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("amount_rub", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="operations"),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("connection_id", "source_key", name="uq_accruals_connection_source"),
    )
    op.create_index("ix_accruals_connection_id", "accruals", ["connection_id"])
    op.create_index("ix_accruals_figi", "accruals", ["figi"])
    op.create_index("ix_accruals_event_date", "accruals", ["event_date"])


def downgrade() -> None:
    op.drop_index("ix_accruals_event_date", table_name="accruals")
    op.drop_index("ix_accruals_figi", table_name="accruals")
    op.drop_index("ix_accruals_connection_id", table_name="accruals")
    op.drop_table("accruals")
