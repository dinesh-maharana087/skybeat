"""Index existing diagnostics for bounded age retention.

Revision ID: 5a12e1c0d9f4
Revises: c1436a7392a9
"""

from collections.abc import Sequence

from alembic import op

revision: str = "5a12e1c0d9f4"
down_revision: str | None = "c1436a7392a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_device_log_entries_retention", "device_log_entries", ["received_at", "id"]
    )
    op.create_index("ix_device_log_sources_retention", "device_log_sources", ["checked_at"])


def downgrade() -> None:
    op.drop_index("ix_device_log_sources_retention", table_name="device_log_sources")
    op.drop_index("ix_device_log_entries_retention", table_name="device_log_entries")
