"""add user full name

Revision ID: c3d9a1f07e55
Revises: 65af290f21b4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d9a1f07e55"
down_revision: str | None = "65af290f21b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "full_name")
