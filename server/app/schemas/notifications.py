"""Strict project notification configuration requests."""

from pydantic import Field, field_validator

from app.schemas.dashboard_management import DashboardManagementRequest, canonical_uuid
from app.users.service import normalize_email


class ProjectNotificationUpdateRequest(DashboardManagementRequest):
    recipients: list[str] = Field(default_factory=list, max_length=100)
    device_offline_enabled: bool
    device_recovered_enabled: bool
    gpu_degraded_enabled: bool
    gpu_recovered_enabled: bool

    @field_validator("recipients")
    @classmethod
    def normalized_recipients(cls, value: list[str]) -> list[str]:
        normalized = [normalize_email(item) for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate recipient")
        return sorted(normalized)


def project_identifier(value: str) -> str:
    return canonical_uuid(value)
