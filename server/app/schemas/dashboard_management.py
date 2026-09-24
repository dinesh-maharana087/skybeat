"""Strict request models for authenticated dashboard management mutations."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _label(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid label")
    normalized = value.strip()
    if not normalized or any(
        ord(character) < 32 or ord(character) == 127 for character in normalized
    ):
        raise ValueError("invalid label")
    return normalized


def canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid identifier")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ValueError("invalid identifier") from error
    if str(parsed) != value:
        raise ValueError("invalid identifier")
    return value


class DashboardManagementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProjectCreateRequest(DashboardManagementRequest):
    name: str = Field(min_length=1, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def project_name(cls, value: object) -> str:
        return _label(value)


class DeviceEnrollRequest(DashboardManagementRequest):
    name: str = Field(min_length=1, max_length=128)
    project_id: str
    gpu_monitoring_enabled: bool = True
    expected_gpu_min_count: int = Field(default=1, ge=0, le=64)

    @field_validator("name", mode="before")
    @classmethod
    def device_name(cls, value: object) -> str:
        return _label(value)

    @field_validator("project_id")
    @classmethod
    def project_uuid(cls, value: object) -> str:
        return canonical_uuid(value)

    @model_validator(mode="after")
    def disabled_gpu_policy_is_empty(self) -> "DeviceEnrollRequest":
        if not self.gpu_monitoring_enabled and self.expected_gpu_min_count != 0:
            raise ValueError("disabled GPU monitoring requires zero expected GPUs")
        return self


class DeviceProjectUpdateRequest(DashboardManagementRequest):
    project_id: str

    @field_validator("project_id")
    @classmethod
    def project_uuid(cls, value: object) -> str:
        return canonical_uuid(value)


class DeviceMonitoringUpdateRequest(DashboardManagementRequest):
    enabled: bool
