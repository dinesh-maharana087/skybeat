"""stage03 availability incidents notifications

Revision ID: 625bfa1677df
Revises: 1b2785bb39ef
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "625bfa1677df"
down_revision: str | None = "1b2785bb39ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
    op.add_column(
        "devices",
        sa.Column("availability_state", sa.String(16), server_default="ONLINE", nullable=False),
    )
    op.create_check_constraint(
        "ck_devices_state", "devices", "availability_state IN ('ONLINE', 'SUSPECT', 'OFFLINE')"
    )
    op.create_table(
        "incidents",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "incident_uuid", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("incident_type", sa.String(32), nullable=False),
        sa.Column("opened_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("detected_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("close_reason", sa.String(64), nullable=True),
        sa.Column("current_reason", sa.String(64), nullable=True),
        sa.Column(
            "active_key",
            sa.String(128),
            sa.Computed(
                "CASE WHEN closed_at IS NULL THEN CONCAT(device_id, ':', incident_type) "
                "ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("incident_type IN ('AVAILABILITY', 'GPU')", name="ck_incidents_type"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_uuid"),
        sa.UniqueConstraint("active_key", name="uq_incidents_active_key"),
        **options,
    )
    op.create_index(
        "ix_incidents_device_type_closed", "incidents", ["device_id", "incident_type", "closed_at"]
    )
    op.create_table(
        "alert_events",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "event_uuid", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("incident_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("detected_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("project_name_snapshot", sa.String(128), nullable=False),
        sa.Column("device_name_snapshot", sa.String(128), nullable=False),
        sa.Column("reason_snapshot", sa.String(128), nullable=True),
        sa.Column("details", mysql.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "event_kind IN ('DEVICE_OFFLINE', 'DEVICE_RECOVERED', 'GPU_DEGRADED', 'GPU_RECOVERED')",
            name="ck_alert_events_kind",
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_uuid"),
        sa.UniqueConstraint("incident_id", "event_kind", name="uq_alert_events_incident_kind"),
        **options,
    )
    op.create_index("ix_alert_events_device_occurred", "alert_events", ["device_id", "occurred_at"])
    op.create_table(
        "notification_deliveries",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "delivery_uuid", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("event_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("recipient_key", sa.String(64), nullable=False),
        sa.Column("destination_snapshot", sa.String(320), nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_count", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("next_attempt_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "lease_token", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=True
        ),
        sa.Column("lease_expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("superseded_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_error_category", sa.String(64), nullable=True),
        sa.Column("provider_message_id", sa.String(256), nullable=True),
        sa.Column("cancel_reason", sa.String(64), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "channel IN ('EMAIL', 'SMS')", name="ck_notification_deliveries_channel"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'RETRY_WAIT', "
            "'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_notification_deliveries_status",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["alert_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_uuid"),
        sa.UniqueConstraint(
            "event_id",
            "channel",
            "recipient_key",
            name="uq_notification_deliveries_event_channel_recipient",
        ),
        **options,
    )
    op.create_index(
        "ix_notification_deliveries_due", "notification_deliveries", ["status", "next_attempt_at"]
    )
    op.create_index(
        "ix_notification_deliveries_lease",
        "notification_deliveries",
        ["status", "lease_expires_at"],
    )
    op.create_table(
        "notification_attempts",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("delivery_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("attempt_no", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("provider_message_id", sa.String(256), nullable=True),
        sa.ForeignKeyConstraint(
            ["delivery_id"], ["notification_deliveries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_id", "attempt_no", name="uq_notification_attempts_delivery_attempt"
        ),
        **options,
    )


def downgrade() -> None:
    op.drop_table("notification_attempts")
    op.drop_index("ix_notification_deliveries_lease", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_due", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_alert_events_device_occurred", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_incidents_device_type_closed", table_name="incidents")
    op.drop_table("incidents")
    op.drop_constraint("ck_devices_state", "devices", type_="check")
    op.drop_column("devices", "availability_state")
