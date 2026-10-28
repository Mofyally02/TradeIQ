"""store the latest accepted EA diagnostic snapshot"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e4f7a2c830"
down_revision: str | None = "91f2d86c4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("device_connectors", sa.Column("last_diagnostics", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("device_connectors", "last_diagnostics")