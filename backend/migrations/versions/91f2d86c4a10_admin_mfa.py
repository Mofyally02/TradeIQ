"""admin MFA enrollment and session verification

Revision ID: 91f2d86c4a10
Revises: 8d4e21a7c901
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "91f2d86c4a10"
down_revision: str | None = "8d4e21a7c901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "admin_mfa",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("admin_mfa")
    op.drop_column("user_sessions", "mfa_verified_at")
