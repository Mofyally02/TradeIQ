"""admin roles, per-user MT5 method and platform settings

Revision ID: f2c8b5a1d703
Revises: e7a1c4d92b36
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8b5a1d703"
down_revision: str | None = "e7a1c4d92b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("role", sa.String(length=16), nullable=False, server_default="user")
    )
    op.add_column("users", sa.Column("mt5_method", sa.String(length=16), nullable=True))
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_column("users", "mt5_method")
    op.drop_column("users", "role")
