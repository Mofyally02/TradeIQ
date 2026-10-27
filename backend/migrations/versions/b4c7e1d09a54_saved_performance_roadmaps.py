"""persist per-user roadmap snapshots and progress

Revision ID: b4c7e1d09a54
Revises: b4c7e1d09a53
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c7e1d09a54"
down_revision: str | None = "b4c7e1d09a53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance_roadmaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column(
            "progress_status",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("progress_notes", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "progress_status IN ('pending', 'in_progress', 'completed', 'adjusted')",
            name="ck_performance_roadmaps_progress_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_performance_roadmaps_user_generated",
        "performance_roadmaps",
        ["user_id", "generated_at"],
    )
    op.create_index(
        op.f("ix_performance_roadmaps_user_id"),
        "performance_roadmaps",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_performance_roadmaps_account_id"),
        "performance_roadmaps",
        ["account_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_performance_roadmaps_account_id"), table_name="performance_roadmaps")
    op.drop_index(op.f("ix_performance_roadmaps_user_id"), table_name="performance_roadmaps")
    op.drop_index("ix_performance_roadmaps_user_generated", table_name="performance_roadmaps")
    op.drop_table("performance_roadmaps")
