import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError

from app.db import database_utc
from app.devices.service import AuthenticationFailed, Conflict, GPUPolicy, IdentityError
from app.models import AuditEvent, Device, DeviceCredential

pytestmark = pytest.mark.mysql


def enroll(identity, **kwargs):
    project = identity.create_project(f"Test {uuid4()}")
    return identity.enroll(project.public_id, "Worker", **kwargs)


def test_migration_and_connection_settings(mysql_database):
    assert mysql_database.ready()
    tables = inspect(mysql_database.engine).get_table_names()
    assert {"projects", "devices", "device_credentials", "audit_events"} <= set(tables)
    with mysql_database.transaction() as session:
        version, tz, charset, isolation = session.execute(
            text(
                "SELECT VERSION(), @@session.time_zone, @@character_set_connection, "
                "@@transaction_isolation"
            )
        ).one()
        assert version.startswith("8.")
        assert tz == "+00:00"
        assert charset == "utf8mb4"
        assert isolation == "READ-COMMITTED"
        engines = (
            session.execute(
                text("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
            )
            .scalars()
            .all()
        )
        assert set(engines) == {"InnoDB"}


def test_enrollment_digest_only_and_binding(identity, mysql_database):
    first, second = enroll(identity), enroll(identity)
    assert UUID(first.device.device_uuid).version == 4
    assert first.device.device_uuid != second.device.device_uuid
    token = first.credential.token.get_secret_value()
    with mysql_database.transaction() as session:
        credential = session.scalar(
            select(DeviceCredential).where(
                DeviceCredential.credential_id == first.credential.credential_id
            )
        )
        assert credential.token_digest == hashlib.sha256(token.encode("ascii")).digest()
        assert not any("secret" in column.name for column in DeviceCredential.__table__.columns)
        device = identity.authenticate(session, first.device.device_uuid, token)
        assert device.id == first.device.id
        with pytest.raises(AuthenticationFailed):
            identity.authenticate(session, second.device.device_uuid, token)
    with mysql_database.transaction() as session:
        audit = session.scalars(
            select(AuditEvent).where(AuditEvent.device_id == first.device.id)
        ).all()
        assert {entry.action for entry in audit} >= {"device.enrolled", "credential.created"}
        assert all(token not in str(entry.details) for entry in audit)


def test_rotation_overlap_revocation_expiration_and_disable(identity, mysql_database):
    enrolled = enroll(identity)
    device_uuid = enrolled.device.device_uuid
    old_token = enrolled.credential.token.get_secret_value()
    rotated = identity.rotate(device_uuid)
    new_token = rotated.token.get_secret_value()
    with pytest.raises(Conflict):
        identity.rotate(device_uuid)
    with mysql_database.transaction() as session:
        now = database_utc(session)
        previous = session.scalar(
            select(DeviceCredential).where(
                DeviceCredential.credential_id == enrolled.credential.credential_id
            )
        )
        assert now < previous.expires_at <= now + timedelta(hours=24)
        assert identity.authenticate(session, device_uuid, old_token).id == enrolled.device.id
        assert identity.authenticate(session, device_uuid, new_token).id == enrolled.device.id
    identity.revoke(device_uuid, enrolled.credential.credential_id)
    with mysql_database.transaction() as session:
        with pytest.raises(AuthenticationFailed):
            identity.authenticate(session, device_uuid, old_token)
    identity.set_enabled(device_uuid, False)
    with mysql_database.transaction() as session:
        with pytest.raises(AuthenticationFailed):
            identity.authenticate(session, device_uuid, new_token)
    identity.set_enabled(device_uuid, True)
    with mysql_database.transaction() as session:
        identity.authenticate(session, device_uuid, new_token)
        current = session.scalar(
            select(DeviceCredential).where(DeviceCredential.credential_id == rotated.credential_id)
        )
        current.expires_at = database_utc(session) - timedelta(seconds=1)
    with mysql_database.transaction() as session:
        with pytest.raises(AuthenticationFailed):
            identity.authenticate(session, device_uuid, new_token)


def test_rename_move_and_policy_preserve_identity(identity, mysql_database):
    enrolled = enroll(identity)
    destination = identity.create_project("Destination")
    device_uuid = enrolled.device.device_uuid
    renamed = identity.rename(device_uuid, "New label")
    moved = identity.move(device_uuid, destination.public_id)
    policy = GPUPolicy(min_count=2, uuids=("GPU-example-A", "GPU-example-B"))
    updated = identity.set_gpu_policy(device_uuid, policy)
    assert renamed.name == "New label"
    assert moved.project_id == destination.id
    assert updated.id == enrolled.device.id
    assert updated.device_uuid == device_uuid
    assert updated.expected_gpu_min_count == 2
    assert updated.expected_gpu_uuids == list(policy.uuids)
    with mysql_database.transaction() as session:
        identity.authenticate(session, device_uuid, enrolled.credential.token.get_secret_value())
        actions = session.scalars(
            select(AuditEvent.action).where(AuditEvent.device_id == updated.id)
        )
        assert {"device.renamed", "device.moved", "device.gpu_policy_changed"} <= set(actions)


def test_rollback_preserves_database(identity, mysql_database):
    enrolled = enroll(identity)
    with pytest.raises(RuntimeError):
        with mysql_database.transaction() as session:
            device = session.get(Device, enrolled.device.id)
            device.name = "Must roll back"
            session.flush()
            raise RuntimeError("simulated application failure")
    assert identity.get_device(enrolled.device.device_uuid).name == "Worker"


def test_concurrent_rotations_enforce_two_active(identity, mysql_database):
    enrolled = enroll(identity)

    def rotate():
        try:
            return identity.rotate(enrolled.device.device_uuid)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sum(result is not None for result in results) == 1
    with mysql_database.transaction() as session:
        credentials = session.scalars(
            select(DeviceCredential).where(DeviceCredential.device_id == enrolled.device.id)
        ).all()
        assert len(credentials) == 2


def test_device_row_lock_timeout_is_bounded(identity, mysql_database):
    enrolled = enroll(identity)
    with mysql_database.transaction() as lock_holder:
        lock_holder.execute(select(Device).where(Device.id == enrolled.device.id).with_for_update())
        with pytest.raises(OperationalError) as error:
            identity.rename(enrolled.device.device_uuid, "Contended")
        assert error.value.orig.args[0] == 1205
    assert identity.get_device(enrolled.device.device_uuid).name == "Worker"


def test_reenable_starts_new_baseline_and_disabled_project_refuses_enrollment(identity):
    enrolled = enroll(identity)
    before = enrolled.device.monitoring_started_at
    identity.set_enabled(enrolled.device.device_uuid, False)
    enabled = identity.set_enabled(enrolled.device.device_uuid, True)
    assert enabled.monitoring_started_at > before
    project = identity.create_project("Inactive")
    identity.update_project(project.public_id, is_active=False)
    with pytest.raises(Conflict):
        identity.enroll(project.public_id, "Disallowed")


@pytest.mark.parametrize(
    "policy",
    [
        {"min_count": -1},
        {"min_count": 65},
        {"uuids": ("duplicate", "duplicate")},
        {"monitoring_enabled": False, "min_count": 1},
        {"uuids": ("bad\nvalue",)},
    ],
)
def test_invalid_gpu_policy_is_rejected(policy):
    with pytest.raises(IdentityError):
        GPUPolicy(**policy)
