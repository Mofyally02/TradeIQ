"""add MetaApi account mapping

Revision ID: 65af290f21b4
Revises: b72a9a51c021
Create Date: 2026-10-23 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "65af290f21b4"
down_revision: str | None = "b72a9a51c021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account_connections",
        sa.Column("provider_account_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "account_connections",
        sa.Column("provisioning_transaction_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_connections", "provisioning_transaction_id")
    op.drop_column("account_connections", "provider_account_id")
