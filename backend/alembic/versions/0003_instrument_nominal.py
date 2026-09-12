"""instrument nominal for bond quotes

Revision ID: 0003_instrument_nominal
Revises: 0002_tinkoff_sync
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_instrument_nominal"
down_revision: Union[str, Sequence[str], None] = "0002_tinkoff_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instruments",
        sa.Column("nominal", sa.Numeric(20, 8), nullable=False, server_default="0"),
    )
    op.add_column(
        "instruments",
        sa.Column("nominal_currency", sa.String(length=8), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("instruments", "nominal_currency")
    op.drop_column("instruments", "nominal")
