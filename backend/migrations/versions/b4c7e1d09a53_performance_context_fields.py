"""add structured performance context to trades

Revision ID: b4c7e1d09a53
Revises: b4c7e1d09a52
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c7e1d09a53"
down_revision: str | None = "b4c7e1d09a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("setup", sa.String(120), nullable=True))
    op.add_column("trades", sa.Column("stop_loss", sa.Numeric(20, 8), nullable=True))
    op.add_column("trades", sa.Column("take_profit", sa.Numeric(20, 8), nullable=True))
    op.add_column("trades", sa.Column("mae_r", sa.Numeric(12, 6), nullable=True))
    op.add_column("trades", sa.Column("mfe_r", sa.Numeric(12, 6), nullable=True))
    op.add_column("trades", sa.Column("emotional_state", sa.String(64), nullable=True))
    op.add_column("trades", sa.Column("confluences", sa.JSON(), nullable=True))
    op.add_column("trades", sa.Column("rule_breaks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "rule_breaks")
    op.drop_column("trades", "confluences")
    op.drop_column("trades", "emotional_state")
    op.drop_column("trades", "mfe_r")
    op.drop_column("trades", "mae_r")
    op.drop_column("trades", "take_profit")
    op.drop_column("trades", "stop_loss")
    op.drop_column("trades", "setup")
