"""store recoverable device connector secret

Revision ID: b4c7e1d09a52
Revises: a9b3d6e2f410
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c7e1d09a52"
down_revision: str | None = "a9b3d6e2f410"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("device_connectors", sa.Column("encrypted_secret", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("device_connectors", "encrypted_secret")
