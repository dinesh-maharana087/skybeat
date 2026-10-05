"""Strict request models for one-time agent enrollment intents."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.dashboard_management import DashboardManagementRequest, _label, canonical_uuid


class AgentEnrollmentIntentRequest(DashboardManagementRequest):
    mode: Literal["NEW", "REPLACE"]
    project_id: str | None = None
    device_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    gpu_monitoring_enabled: bool | None = None
    expected_gpu_min_count: int | None = Field(default=None, ge=0, le=64)

    @field_validator("project_id", "device_id")
    @classmethod
    def target_uuid(cls, value: object) -> str | None:
        return None if value is None else canonical_uuid(value)

    @field_validator("name", mode="before")
    @classmethod
    def device_name(cls, value: object) -> str | None:
        return None if value is None else _label(value)

    @field_validator("description", mode="before")
    @classmethod
    def device_description(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("invalid description")
        return _label(value) if value.strip() else None

    @model_validator(mode="after")
    def target_is_complete_and_unambiguous(self) -> "AgentEnrollmentIntentRequest":
        if self.mode == "NEW":
            if self.project_id is None or self.name is None or self.device_id is not None:
                raise ValueError("new enrollment target is invalid")
            if self.gpu_monitoring_enabled is None:
                self.gpu_monitoring_enabled = True
            if self.expected_gpu_min_count is None:
                self.expected_gpu_min_count = 1
            if not self.gpu_monitoring_enabled and self.expected_gpu_min_count != 0:
                raise ValueError("disabled GPU monitoring requires zero expected GPUs")
        elif (
            self.device_id is None
            or self.project_id is not None
            or self.name is not None
            or self.description is not None
            or self.gpu_monitoring_enabled is not None
            or self.expected_gpu_min_count is not None
        ):
            raise ValueError("replacement enrollment target is invalid")
        return self
