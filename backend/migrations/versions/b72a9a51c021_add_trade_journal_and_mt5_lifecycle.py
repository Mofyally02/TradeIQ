"""add trade journal and mt5 lifecycle fields

Revision ID: b72a9a51c021
Revises: aa91c301df54
Create Date: 2026-10-23 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b72a9a51c021"
down_revision: str | None = "aa91c301df54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mt5_orders", sa.Column("stop_loss", sa.Numeric(20, 8), nullable=True))
    op.add_column("mt5_orders", sa.Column("take_profit", sa.Numeric(20, 8), nullable=True))
    op.add_column(
        "mt5_deals",
        sa.Column("position_identifier", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "mt5_deals",
        sa.Column("entry_type", sa.String(length=16), server_default="in", nullable=False),
    )
    op.create_index(
        op.f("ix_mt5_deals_position_identifier"),
        "mt5_deals",
        ["position_identifier"],
        unique=False,
    )
    op.add_column("mt5_positions", sa.Column("entry_price", sa.Numeric(20, 8), nullable=True))
    op.add_column("mt5_positions", sa.Column("current_price", sa.Numeric(20, 8), nullable=True))
    op.add_column("mt5_positions", sa.Column("stop_loss", sa.Numeric(20, 8), nullable=True))
    op.add_column("mt5_positions", sa.Column("take_profit", sa.Numeric(20, 8), nullable=True))
    op.add_column("mt5_positions", sa.Column("floating_pnl", sa.Numeric(20, 6), nullable=True))
    with op.batch_alter_table("trades") as batch_op:
        batch_op.create_unique_constraint(
            "uq_trades_account_external_id",
            ["account_id", "external_id"],
        )
    with op.batch_alter_table("mt5_deals") as batch_op:
        batch_op.alter_column("entry_type", server_default=None)
    op.create_table(
        "trade_journal_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trade_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_id", "section_key"),
    )
    op.create_index(
        op.f("ix_trade_journal_sections_trade_id"),
        "trade_journal_sections",
        ["trade_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trade_journal_sections_trade_id"), table_name="trade_journal_sections")
    op.drop_table("trade_journal_sections")
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_constraint("uq_trades_account_external_id", type_="unique")
    op.drop_column("mt5_positions", "floating_pnl")
    op.drop_column("mt5_positions", "take_profit")
    op.drop_column("mt5_positions", "stop_loss")
    op.drop_column("mt5_positions", "current_price")
    op.drop_column("mt5_positions", "entry_price")
    op.drop_index(op.f("ix_mt5_deals_position_identifier"), table_name="mt5_deals")
    op.drop_column("mt5_deals", "entry_type")
    op.drop_column("mt5_deals", "position_identifier")
    op.drop_column("mt5_orders", "take_profit")
    op.drop_column("mt5_orders", "stop_loss")
