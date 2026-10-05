"""Add optional descriptions to pending enrollment and enrolled devices.

Revision ID: 81be693a0806
Revises: e43a8c9b0d11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "81be693a0806"
down_revision: str | None = "e43a8c9b0d11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_enrollments", sa.Column("description", sa.String(512), nullable=True))
    op.add_column("devices", sa.Column("description", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "description")
    op.drop_column("agent_enrollments", "description")
