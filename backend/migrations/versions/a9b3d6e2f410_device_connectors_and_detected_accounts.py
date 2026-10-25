"""device connectors and detected MT5 accounts

Revision ID: a9b3d6e2f410
Revises: f2c8b5a1d703
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9b3d6e2f410"
down_revision: str | None = "f2c8b5a1d703"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_connectors",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "detected_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("server", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("balance", sa.Numeric(20, 6), nullable=True),
        sa.Column("equity", sa.Numeric(20, 6), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "login", name="uq_detected_accounts_user_login"),
    )
    op.create_index("ix_detected_accounts_user_id", "detected_accounts", ["user_id"])
    op.add_column("trade_plans", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_trade_plans_account_id", "trade_plans", "trading_accounts", ["account_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_trade_plans_account_id", "trade_plans", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_trade_plans_account_id", table_name="trade_plans")
    op.drop_constraint("fk_trade_plans_account_id", "trade_plans", type_="foreignkey")
    op.drop_column("trade_plans", "account_id")
    op.drop_index("ix_detected_accounts_user_id", table_name="detected_accounts")
    op.drop_table("detected_accounts")
    op.drop_table("device_connectors")
