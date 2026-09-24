"""Canonical dashboard management adapter for authenticated UI mutations."""

from dataclasses import dataclass, field

from pydantic import SecretStr

from app.db import Database
from app.devices.credentials import GeneratedCredential
from app.devices.service import GPUPolicy, IdentityService
from app.models import Device, Project
from app.schemas.dashboard_management import (
    DeviceEnrollRequest,
    DeviceMonitoringUpdateRequest,
    DeviceProjectUpdateRequest,
    ProjectCreateRequest,
)


def _project_view(project: Project) -> dict[str, str]:
    return {"project_id": project.public_id, "name": project.name}


def _device_view(device: Device, *, project_id: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "device_id": device.device_uuid,
        "name": device.name,
        "monitoring_enabled": device.monitoring_enabled,
        "gpu_monitoring_enabled": device.gpu_monitoring_enabled,
        "expected_gpu_min_count": device.expected_gpu_min_count,
    }
    if project_id is not None:
        result["project_id"] = project_id
    return result


@dataclass(frozen=True)
class EnrollmentResult:
    device: dict[str, object]
    credential: GeneratedCredential = field(repr=False)


class DashboardManagementService:
    """Delegate dashboard writes to the existing identity administration service."""

    def __init__(self, database: Database, *, actor: str) -> None:
        self._identity = IdentityService(database, actor=actor)

    def create_project(self, request: ProjectCreateRequest) -> dict[str, str]:
        return _project_view(self._identity.create_project(name=request.name))

    def enroll_device(self, request: DeviceEnrollRequest) -> EnrollmentResult:
        enrollment = self._identity.enroll(
            request.project_id,
            request.name,
            policy=GPUPolicy(
                monitoring_enabled=request.gpu_monitoring_enabled,
                min_count=request.expected_gpu_min_count,
            ),
        )
        return EnrollmentResult(
            device=_device_view(enrollment.device, project_id=request.project_id),
            credential=enrollment.credential,
        )

    def move_device(
        self, device_uuid: str, request: DeviceProjectUpdateRequest
    ) -> dict[str, object]:
        device = self._identity.move(device_uuid, request.project_id)
        return _device_view(device, project_id=request.project_id)

    def set_device_enabled(
        self, device_uuid: str, request: DeviceMonitoringUpdateRequest
    ) -> dict[str, object]:
        return _device_view(self._identity.set_enabled(device_uuid, request.enabled))


def enrollment_credential_value(result: EnrollmentResult) -> SecretStr:
    """Keep one-time credential extraction explicit at the response boundary."""

    return result.credential.token
