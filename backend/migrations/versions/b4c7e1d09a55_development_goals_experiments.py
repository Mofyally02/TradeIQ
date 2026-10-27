"""per-user development goals and experiments

Revision ID: b4c7e1d09a55
Revises: b4c7e1d09a54
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c7e1d09a55"
down_revision: str | None = "b4c7e1d09a54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "development_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=12), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("baseline_sample", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "direction IN ('increase', 'decrease')", name="ck_development_goals_direction"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'achieved', 'paused', 'dropped')",
            name="ck_development_goals_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_development_goals_user_id"), "development_goals", ["user_id"])
    op.create_index(
        "ix_development_goals_user_status", "development_goals", ["user_id", "status"]
    )
    op.create_table(
        "development_experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("min_trades", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned', 'running', 'concluded', 'abandoned')",
            name="ck_development_experiments_status",
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["development_goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_development_experiments_user_id"), "development_experiments", ["user_id"]
    )
    op.create_index(
        op.f("ix_development_experiments_goal_id"), "development_experiments", ["goal_id"]
    )
    op.create_index(
        "ix_development_experiments_user_status",
        "development_experiments",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_development_experiments_user_status", table_name="development_experiments")
    op.drop_index(op.f("ix_development_experiments_goal_id"), table_name="development_experiments")
    op.drop_index(op.f("ix_development_experiments_user_id"), table_name="development_experiments")
    op.drop_table("development_experiments")
    op.drop_index("ix_development_goals_user_status", table_name="development_goals")
    op.drop_index(op.f("ix_development_goals_user_id"), table_name="development_goals")
    op.drop_table("development_goals")
