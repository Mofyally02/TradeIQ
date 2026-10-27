"""admin RBAC, audit history and incidents

Revision ID: 8d4e21a7c901
Revises: b4c7e1d09a55
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "8d4e21a7c901"
down_revision: str | None = "b4c7e1d09a55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE_PERMISSIONS = {
    "super_admin": [
        "overview.read", "users.read", "users.manage_roles", "users.manage_status",
        "accounts.read", "connectors.read", "sync.read", "data_quality.read",
        "data_quality.resolve", "journal_quality.read",
        "intelligence.read", "taxonomy.manage", "risk_rules.manage", "development.manage",
        "experiments.manage", "incidents.manage", "audit.read", "settings.manage",
    ],
    "platform_ops": [
        "overview.read", "users.read", "accounts.read", "connectors.read", "sync.read",
        "data_quality.read", "data_quality.resolve", "journal_quality.read", "incidents.manage",
    ],
    "data_quality": [
        "overview.read", "accounts.read", "sync.read", "data_quality.read",
        "data_quality.resolve", "journal_quality.read",
    ],
    "intelligence_admin": [
        "overview.read", "journal_quality.read", "intelligence.read", "taxonomy.manage",
        "risk_rules.manage", "development.manage", "experiments.manage",
    ],
    "support_agent": ["overview.read", "users.read", "accounts.read", "incidents.manage"],
    "read_only_auditor": [
        "overview.read", "users.read", "accounts.read", "connectors.read", "sync.read",
        "data_quality.read", "journal_quality.read", "intelligence.read", "audit.read",
    ],
}

PERMISSIONS = {
    "overview.read": "View operational overview",
    "users.read": "View limited user identity and workspace metadata",
    "users.manage_roles": "Assign administrator roles",
    "users.manage_status": "Suspend or restore user access and revoke sessions",
    "accounts.read": "View trading account operational metadata",
    "connectors.read": "View connector health and safe diagnostic details",
    "sync.read": "View synchronization run history",
    "data_quality.read": "View source-to-journal data quality signals",
    "data_quality.resolve": "Resolve or accept a documented data quality issue",
    "journal_quality.read": "View aggregate journal completeness without private notes",
    "intelligence.read": "View intelligence service health and aggregate status",
    "taxonomy.manage": "Manage shared strategy taxonomy",
    "risk_rules.manage": "Manage risk policy definitions",
    "development.manage": "Manage goal templates",
    "experiments.manage": "Manage analytical evaluations",
    "incidents.manage": "Create and update platform incidents",
    "audit.read": "Read immutable administrative audit records",
    "settings.manage": "Change platform-wide settings",
}


def upgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default="user",
    )
    op.add_column(
        "users", sa.Column("status", sa.String(length=16), server_default="active", nullable=False)
    )
    op.create_table(
        "admin_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "admin_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "admin_role_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["admin_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["admin_permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id"),
    )
    op.create_index("ix_admin_role_permissions_role_id", "admin_role_permissions", ["role_id"])
    op.create_index(
        "ix_admin_role_permissions_permission_id", "admin_role_permissions", ["permission_id"]
    )
    op.create_table(
        "user_role_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=16), server_default="platform", nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope_type IN ('platform', 'account')", name="ck_user_role_scope_type"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["admin_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", "scope_type", "scope_id"),
    )
    op.create_index("ix_user_role_assignments_user_id", "user_role_assignments", ["user_id"])
    op.create_index("ix_user_role_assignments_role_id", "user_role_assignments", ["role_id"])
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=48), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=24), server_default="success", nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_logs_actor_user_id", "admin_audit_logs", ["actor_user_id"])
    op.create_index(
        "ix_admin_audit_actor_created", "admin_audit_logs", ["actor_user_id", "created_at"]
    )
    op.create_table(
        "platform_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="medium", nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="open", nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'accepted_exception')",
            name="ck_platform_incidents_status",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_platform_incidents_severity",
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_incidents_status_created", "platform_incidents", ["status", "created_at"]
    )

    connection = op.get_bind()
    role_ids: dict[str, object] = {}
    permission_ids: dict[str, object] = {}
    for role, permissions in ROLE_PERMISSIONS.items():
        role_id = uuid4()
        role_ids[role] = role_id
        connection.execute(
            sa.text(
                "INSERT INTO admin_roles (id, name, description, created_at) "
                "VALUES (:id, :name, :description, CURRENT_TIMESTAMP)"
            ),
            {"id": role_id, "name": role, "description": role.replace("_", " ").title()},
        )
        for key in permissions:
            if key not in permission_ids:
                permission_id = uuid4()
                permission_ids[key] = permission_id
                connection.execute(
                    sa.text(
                        "INSERT INTO admin_permissions (id, key, description) "
                        "VALUES (:id, :key, :description)"
                    ),
                    {"id": permission_id, "key": key, "description": PERMISSIONS[key]},
                )
            connection.execute(
                sa.text(
                    "INSERT INTO admin_role_permissions (id, role_id, permission_id) "
                    "VALUES (:id, :role_id, :permission_id)"
                ),
                {
                    "id": uuid4(),
                    "role_id": role_id,
                    "permission_id": permission_ids[key],
                },
            )
    super_id = role_ids["super_admin"]
    legacy_admin_ids = connection.execute(
        sa.text("SELECT id FROM users WHERE role = 'admin'")
    ).scalars()
    for user_id in legacy_admin_ids:
        connection.execute(
            sa.text(
                "INSERT INTO user_role_assignments "
                "(id, user_id, role_id, scope_type, scope_id, assigned_by, expires_at, created_at) "
                "VALUES (:id, :user_id, :role_id, 'platform', NULL, NULL, NULL, CURRENT_TIMESTAMP)"
            ),
            {"id": uuid4(), "user_id": user_id, "role_id": super_id},
        )


def downgrade() -> None:
    op.drop_index("ix_platform_incidents_status_created", table_name="platform_incidents")
    op.drop_table("platform_incidents")
    op.drop_index("ix_admin_audit_actor_created", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_actor_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_user_role_assignments_role_id", table_name="user_role_assignments")
    op.drop_index("ix_user_role_assignments_user_id", table_name="user_role_assignments")
    op.drop_table("user_role_assignments")
    op.drop_index("ix_admin_role_permissions_permission_id", table_name="admin_role_permissions")
    op.drop_index("ix_admin_role_permissions_role_id", table_name="admin_role_permissions")
    op.drop_table("admin_role_permissions")
    op.drop_table("admin_permissions")
    op.drop_table("admin_roles")
    op.drop_column("users", "status")
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="user",
    )
