"""rule-based trading agent insights

Revision ID: e5a2c8f31b76
Revises: d1e4f7a2c830
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a2c8f31b76"
down_revision: str | None = "d1e4f7a2c830"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("fingerprint", sa.String(length=160), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("confidence", sa.String(length=12), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("effect_size", sa.Float(), nullable=True),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("q_value", sa.Float(), nullable=True),
        sa.Column("est_dollar_impact", sa.Float(), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("holds_out_of_time", sa.Boolean(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="new"),
        sa.Column("feedback", sa.String(length=16), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'seen', 'accepted', 'dismissed', 'experiment_running', 'resolved')",
            name="ck_agent_insights_status",
        ),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback IN ('useful', 'not_useful', 'wrong', 'already_knew')",
            name="ck_agent_insights_feedback",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fingerprint", name="uq_agent_insights_user_fingerprint"),
    )
    op.create_index(op.f("ix_agent_insights_user_id"), "agent_insights", ["user_id"])
    op.create_index(op.f("ix_agent_insights_account_id"), "agent_insights", ["account_id"])
    op.create_index(
        "ix_agent_insights_user_active_priority",
        "agent_insights",
        ["user_id", "active", "priority_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_insights_user_active_priority", table_name="agent_insights")
    op.drop_index(op.f("ix_agent_insights_account_id"), table_name="agent_insights")
    op.drop_index(op.f("ix_agent_insights_user_id"), table_name="agent_insights")
    op.drop_table("agent_insights")
