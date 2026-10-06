"""Real MySQL coverage for the bounded operational Overview projection."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.dashboard.read import REQUIRED_ATTENTION_PREVIEW_LIMIT, DashboardReadService
from app.db import database_utc
from app.models import Device

pytestmark = pytest.mark.mysql


def test_required_attention_count_order_preview_and_never_seen_exclusion(identity, mysql_database):
    before = DashboardReadService(mysql_database).overview()["counts"]["required_attention"]
    project = identity.create_project(f"Overview {uuid4()}")
    cases = [
        ("offline-gpu", "OFFLINE", "DRIVER_ERROR"),
        ("offline", "OFFLINE", "OK"),
        ("suspect-gpu", "SUSPECT", "GPU_MISSING"),
        ("suspect", "SUSPECT", "OK"),
        ("online-gpu", "ONLINE", "NVIDIA_SMI_FAILED"),
        ("healthy", "ONLINE", "OK"),
        ("never-seen", "ONLINE", "UNKNOWN"),
    ]
    enrolled = [identity.enroll(project.public_id, name) for name, _, _ in cases]
    with mysql_database.transaction() as session:
        now = database_utc(session)
        for index, ((_, state, gpu), created) in enumerate(zip(cases, enrolled, strict=True)):
            device = session.scalar(select(Device).where(Device.id == created.device.id))
            assert device is not None
            device.availability_state = state
            device.gpu_effective_state = gpu
            device.gpu_monitoring_enabled = True
            device.last_seen_at = None if index == 6 else now - timedelta(minutes=index + 1)

    payload = DashboardReadService(mysql_database).overview()
    names = [item["name"] for item in payload["required_attention"]]
    assert payload["counts"]["required_attention"] == before + 5
    assert "healthy" not in names and "never-seen" not in names
    tiers = {
        ("OFFLINE", True): 0,
        ("OFFLINE", False): 1,
        ("SUSPECT", True): 2,
        ("SUSPECT", False): 3,
        (None, True): 4,
    }
    ordered = [
        tiers[(item["communication_attention"], item["gpu_attention"])]
        for item in payload["required_attention"]
    ]
    assert ordered == sorted(ordered)
    assert len(payload["required_attention"]) <= REQUIRED_ATTENTION_PREVIEW_LIMIT


def test_required_attention_preview_is_bounded_but_count_is_exact(identity, mysql_database):
    before = DashboardReadService(mysql_database).overview()["counts"]["required_attention"]
    project = identity.create_project(f"Overview cap {uuid4()}")
    enrolled = [
        identity.enroll(project.public_id, f"offline-{index:02d}")
        for index in range(REQUIRED_ATTENTION_PREVIEW_LIMIT + 2)
    ]
    with mysql_database.transaction() as session:
        now = database_utc(session)
        for index, created in enumerate(enrolled):
            device = session.scalar(select(Device).where(Device.id == created.device.id))
            assert device is not None
            device.last_seen_at = now - timedelta(minutes=index + 1)
            device.availability_state = "OFFLINE"
            device.gpu_effective_state = "OK"
    payload = DashboardReadService(mysql_database).overview()
    assert payload["counts"]["required_attention"] == before + REQUIRED_ATTENTION_PREVIEW_LIMIT + 2
    assert len(payload["required_attention"]) == REQUIRED_ATTENTION_PREVIEW_LIMIT
