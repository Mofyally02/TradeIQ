"""restore provider_account_id for MetaApi

Revision ID: e7a1c4d92b36
Revises: d41e7b2c9a10
"""

import sqlalchemy as sa
from alembic import op

revision = "e7a1c4d92b36"
down_revision = "d41e7b2c9a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account_connections", sa.Column("provider_account_id", sa.String(128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("account_connections", "provider_account_id")
