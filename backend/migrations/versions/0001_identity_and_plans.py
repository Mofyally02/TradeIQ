"""Create users, sessions, and trade plans.

Revision ID: 0001_identity_and_plans
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_identity_and_plans"
down_revision = None
branch_labels = None
depends_on = None

plan_state = sa.Enum(
    "planned", "discarded", "invalidated", name="trade_plan_state", native_enum=False
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_user_expires", "user_sessions", ["user_id", "expires_at"])

    op.create_table(
        "trade_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=5), nullable=False),
        sa.Column("strategy", sa.String(length=120), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("state", plan_state, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_plans_user_id", "trade_plans", ["user_id"])
    op.create_index("ix_trade_plans_user_created", "trade_plans", ["user_id", "created_at"])
    op.create_index(
        "ix_trade_plans_user_state_created", "trade_plans", ["user_id", "state", "created_at"]
    )

    op.create_table(
        "trade_plan_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["trade_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "version_number"),
    )
    op.create_index("ix_trade_plan_versions_plan_id", "trade_plan_versions", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_trade_plan_versions_plan_id", table_name="trade_plan_versions")
    op.drop_table("trade_plan_versions")
    op.drop_index("ix_trade_plans_user_state_created", table_name="trade_plans")
    op.drop_index("ix_trade_plans_user_created", table_name="trade_plans")
    op.drop_index("ix_trade_plans_user_id", table_name="trade_plans")
    op.drop_table("trade_plans")
    op.drop_index("ix_user_sessions_user_expires", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
