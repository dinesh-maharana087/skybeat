from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from app.api.auth import same_origin
from app.config import Settings
from app.dashboard import management
from app.devices.credentials import GeneratedCredential
from app.main import create_app
from app.schemas.dashboard_management import (
    DeviceEnrollRequest,
    DeviceMonitoringUpdateRequest,
    ProjectCreateRequest,
)


def test_application_exposes_a_dashboard_management_service_factory():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test"
    )

    app = create_app(settings)

    assert callable(app.state.dashboard_management_service_factory)


def test_same_origin_retains_existing_origin_and_referer_rules():
    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)

    def request(headers: list[tuple[bytes, bytes]]) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/logout",
                "headers": headers,
                "app": app,
            }
        )

    assert same_origin(request([(b"origin", b"https://testserver")]))
    assert same_origin(request([(b"referer", b"https://testserver/dashboard")]))
    assert not same_origin(request([(b"origin", b"https://other.example")]))


def test_management_request_models_reject_invalid_or_unbounded_values():
    with pytest.raises(ValidationError):
        ProjectCreateRequest(name=" ")
    with pytest.raises(ValidationError):
        ProjectCreateRequest(name="x" * 129)
    with pytest.raises(ValidationError):
        DeviceEnrollRequest(name="device", project_id="not-a-canonical-uuid")
    with pytest.raises(ValidationError):
        DeviceEnrollRequest(
            name="device",
            project_id="e3e70682-c209-4cac-a29f-6fbed82c07cd",
            gpu_monitoring_enabled=False,
            expected_gpu_min_count=1,
        )
    with pytest.raises(ValidationError):
        DeviceMonitoringUpdateRequest(enabled="yes")


def test_dashboard_management_enrollment_delegates_to_identity_service(monkeypatch):
    credential = GeneratedCredential(
        credential_id="e3e70682-c209-4cac-a29f-6fbed82c07cd",
        token=SecretStr("sb1.e3e70682-c209-4cac-a29f-6fbed82c07cd.test-secret"),
        digest=b"x" * 32,
    )
    captured: dict[str, object] = {}

    class FakeIdentityService:
        def __init__(self, database, *, actor):
            captured["database"] = database
            captured["actor"] = actor

        def enroll(self, project_uuid, name, *, policy):
            captured["project_uuid"] = project_uuid
            captured["name"] = name
            captured["policy"] = policy
            return SimpleNamespace(
                device=SimpleNamespace(
                    device_uuid="65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
                    name=name,
                    monitoring_enabled=True,
                    gpu_monitoring_enabled=policy.monitoring_enabled,
                    expected_gpu_min_count=policy.min_count,
                ),
                credential=credential,
            )

    monkeypatch.setattr(management, "IdentityService", FakeIdentityService)
    result = management.DashboardManagementService(
        object(), actor="ops@example.test"
    ).enroll_device(
        DeviceEnrollRequest(
            name="GPU node",
            project_id="e3e70682-c209-4cac-a29f-6fbed82c07cd",
            gpu_monitoring_enabled=True,
            expected_gpu_min_count=2,
        )
    )

    assert captured["actor"] == "ops@example.test"
    assert captured["project_uuid"] == "e3e70682-c209-4cac-a29f-6fbed82c07cd"
    assert captured["name"] == "GPU node"
    assert captured["policy"].monitoring_enabled is True
    assert captured["policy"].min_count == 2
    assert result.device == {
        "device_id": "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
        "name": "GPU node",
        "monitoring_enabled": True,
        "gpu_monitoring_enabled": True,
        "expected_gpu_min_count": 2,
        "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
    }
    assert management.enrollment_credential_value(result).get_secret_value().startswith("sb1.")
    assert "test-secret" not in repr(result)
