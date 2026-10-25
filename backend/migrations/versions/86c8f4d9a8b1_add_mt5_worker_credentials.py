"""add mt5 worker credentials

Revision ID: 86c8f4d9a8b1
Revises: 4df430e079c1
Create Date: 2026-10-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "86c8f4d9a8b1"
down_revision: str | None = "4df430e079c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trading_accounts",
        sa.Column("external_account_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "account_connections",
        sa.Column("connector_token_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_connections", "connector_token_hash")
    op.drop_column("trading_accounts", "external_account_id")
