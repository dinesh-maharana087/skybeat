"""Bounded recent agent journal entries and per-source collection state."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, BINARY, DATETIME, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models import TABLE_OPTIONS, Base


class DeviceLogEntry(Base):
    __tablename__ = "device_log_entries"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "source", "entry_hash", name="uq_device_log_entry_source_hash"
        ),
        Index("ix_device_log_entries_recent", "device_id", "source", "id"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    source: Mapped[str] = mapped_column(String(32))
    entry_hash: Mapped[bytes] = mapped_column(BINARY(32))
    occurred_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    received_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    severity: Mapped[str | None] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(TEXT)


class DeviceLogSource(Base):
    __tablename__ = "device_log_sources"
    __table_args__ = (TABLE_OPTIONS,)

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    checked_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
