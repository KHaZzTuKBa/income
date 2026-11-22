"""user registration, roles and per-user isolation

Revision ID: 0009_user_accounts
Revises: 0008_instrument_sector
Create Date: 2026-11-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_user_accounts"
down_revision: Union[str, Sequence[str], None] = "0008_instrument_sector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=16), nullable=True))
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])
    op.create_index("ix_users_status", "users", ["status"])
    op.execute("UPDATE users SET is_admin = true WHERE id = (SELECT min(id) FROM users)")

    op.add_column("holdings_categories", sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE holdings_categories AS h SET user_id = c.user_id "
        "FROM categories AS c WHERE c.id = h.category_id"
    )
    op.execute("DELETE FROM holdings_categories WHERE user_id IS NULL")
    op.alter_column("holdings_categories", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_holdings_categories_user_id",
        "holdings_categories",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_holdings_categories_user_id", "holdings_categories", ["user_id"])
    op.drop_constraint("uq_holdings_categories_figi", "holdings_categories", type_="unique")
    op.create_unique_constraint(
        "uq_holdings_categories_user_figi", "holdings_categories", ["user_id", "figi"]
    )

    op.drop_index("ix_accounts_broker_account_id", table_name="accounts")
    op.create_index("ix_accounts_broker_account_id", "accounts", ["broker_account_id"])
    op.create_unique_constraint(
        "uq_accounts_connection_broker_id", "accounts", ["connection_id", "broker_account_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_accounts_connection_broker_id", "accounts", type_="unique")
    op.drop_index("ix_accounts_broker_account_id", table_name="accounts")
    op.create_index("ix_accounts_broker_account_id", "accounts", ["broker_account_id"], unique=True)

    op.drop_constraint("uq_holdings_categories_user_figi", "holdings_categories", type_="unique")
    op.create_unique_constraint("uq_holdings_categories_figi", "holdings_categories", ["figi"])
    op.drop_index("ix_holdings_categories_user_id", table_name="holdings_categories")
    op.drop_constraint("fk_holdings_categories_user_id", "holdings_categories", type_="foreignkey")
    op.drop_column("holdings_categories", "user_id")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_constraint("uq_users_phone", "users", type_="unique")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "reviewed_at")
    op.drop_column("users", "is_admin")
    op.drop_column("users", "status")
    op.drop_column("users", "phone")
    op.drop_column("users", "email")
