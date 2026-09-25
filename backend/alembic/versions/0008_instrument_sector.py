"""instrument sector from Invest API

Revision ID: 0008_instrument_sector
Revises: 0007_account_snapshots
Create Date: 2026-09-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_instrument_sector"
down_revision: Union[str, Sequence[str], None] = "0007_account_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instruments",
        sa.Column("sector", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("instruments", "sector")
