"""categories tree and holdings

Revision ID: 0004_categories
Revises: 0003_instrument_nominal
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_categories"
down_revision: Union[str, Sequence[str], None] = "0003_instrument_nominal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("target_share", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "holdings_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("figi", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("figi", name="uq_holdings_categories_figi"),
    )
    op.create_index("ix_holdings_categories_category_id", "holdings_categories", ["category_id"])
    op.create_index("ix_holdings_categories_figi", "holdings_categories", ["figi"])


def downgrade() -> None:
    op.drop_index("ix_holdings_categories_figi", table_name="holdings_categories")
    op.drop_index("ix_holdings_categories_category_id", table_name="holdings_categories")
    op.drop_table("holdings_categories")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")
