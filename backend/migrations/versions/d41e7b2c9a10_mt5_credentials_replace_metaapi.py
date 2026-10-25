"""store encrypted MT5 password, drop MetaApi columns

Revision ID: d41e7b2c9a10
Revises: c3d9a1f07e55
"""

import sqlalchemy as sa
from alembic import op

revision = "d41e7b2c9a10"
down_revision = "c3d9a1f07e55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account_connections", sa.Column("encrypted_password", sa.Text(), nullable=True))
    op.drop_column("account_connections", "provider_account_id")
    op.drop_column("account_connections", "provisioning_transaction_id")


def downgrade() -> None:
    op.add_column(
        "account_connections", sa.Column("provisioning_transaction_id", sa.String(64), nullable=True)
    )
    op.add_column(
        "account_connections", sa.Column("provider_account_id", sa.String(128), nullable=True)
    )
    op.drop_column("account_connections", "encrypted_password")
