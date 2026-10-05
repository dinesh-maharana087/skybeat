import importlib.util
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_device_description_migration_emits_only_nullable_mysql_columns(monkeypatch):
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/81be693a0806_stage12c_device_description.py"
    )
    spec = importlib.util.spec_from_file_location("device_description_migration", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "e43a8c9b0d11"

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql", opts={"as_sql": True, "output_buffer": output}
    )
    monkeypatch.setattr(module, "op", Operations(context))
    module.upgrade()
    statements = output.getvalue()
    assert "ALTER TABLE agent_enrollments ADD COLUMN description VARCHAR(512)" in statements
    assert "ALTER TABLE devices ADD COLUMN description VARCHAR(512)" in statements
    assert "NOT NULL" not in statements
    assert "UPDATE " not in statements


def test_enrollment_token_is_opaque_and_parses_only_its_expected_prefix():
    from app.enrollment.service import EnrollmentToken, TokenRejected

    token = EnrollmentToken.generate("sbe1")

    assert token.value.startswith("sbe1.")
    assert EnrollmentToken.parse(token.value, expected_prefix="sbe1").identifier == token.identifier
    with pytest.raises(TokenRejected):
        EnrollmentToken.parse(token.value, expected_prefix="sbv1")


def test_verification_token_has_a_distinct_opaque_prefix():
    from app.enrollment.service import EnrollmentToken

    token = EnrollmentToken.generate("sbv1")

    assert token.value.startswith("sbv1.")
    parsed = EnrollmentToken.parse(token.value, expected_prefix="sbv1")
    assert parsed.secret_digest == token.secret_digest


@pytest.mark.parametrize(
    "value",
    ["", "sbe1.bad", "sbe1.not-a-uuid.secret", "sbe1.00000000-0000-0000-0000-000000000000.short"],
)
def test_enrollment_token_rejects_malformed_input_without_echoing_it(value):
    from app.enrollment.service import EnrollmentToken, TokenRejected

    with pytest.raises(TokenRejected) as failure:
        EnrollmentToken.parse(value, expected_prefix="sbe1")

    assert str(failure.value) == "Enrollment token is invalid."


def test_durable_enrollment_model_has_separate_single_use_and_receipt_digests():
    from app.models import AgentEnrollment, Device

    columns = AgentEnrollment.__table__.c

    assert {"public_id", "enrollment_digest", "verification_digest", "expires_at"} <= set(
        columns.keys()
    )
    assert columns.enrollment_digest.unique
    assert columns.verification_digest.unique
    assert columns.description.nullable
    assert Device.__table__.c.description.nullable
    assert columns.description.type.length == Device.__table__.c.description.type.length == 512
    constraint_sql = [
        str(constraint.sqltext)
        for constraint in AgentEnrollment.__table__.constraints
        if hasattr(constraint, "sqltext")
    ]
    assert any("NEW" in text and "REPLACE" in text for text in constraint_sql)


def test_enrollment_exchange_is_single_use_and_receipt_is_scoped(mysql_database, identity):
    from app.db import database_utc
    from app.devices.service import GPUPolicy
    from app.enrollment.service import (
        AgentEnrollmentService,
        EnrollmentMode,
        EnrollmentRejected,
        ReceiptRejected,
    )

    project = identity.create_project("Enrollment service project")
    service = AgentEnrollmentService(mysql_database, actor="owner@example.com")
    intent = service.create_intent(
        mode=EnrollmentMode.NEW,
        project_uuid=project.public_id,
        device_name="enrollment-service-device",
        description="  Packing line GPU  ",
        policy=GPUPolicy(),
    )

    assert intent.enrollment.expires_at - intent.enrollment.created_at == timedelta(hours=24)
    assert intent.enrollment.description == "Packing line GPU"

    exchanged = service.exchange(intent.token.value)

    assert exchanged.device.name == "enrollment-service-device"
    assert exchanged.device.description == "Packing line GPU"
    assert not service.verify_receipt(exchanged.verification_token.value).accepted_heartbeat
    with pytest.raises(EnrollmentRejected):
        service.exchange(intent.token.value)
    with pytest.raises(EnrollmentRejected):
        service.exchange(exchanged.verification_token.value)
    with pytest.raises(ReceiptRejected):
        service.verify_receipt(intent.token.value)

    with mysql_database.transaction() as session:
        device = session.get(type(exchanged.device), exchanged.device.id)
        assert device is not None
        device.last_seen_at = database_utc(session)

    assert service.verify_receipt(exchanged.verification_token.value).accepted_heartbeat


def test_replacement_exchange_preserves_existing_device_description(mysql_database, identity):
    from app.devices.service import GPUPolicy
    from app.enrollment.service import AgentEnrollmentService, EnrollmentMode

    project = identity.create_project("Replacement description project")
    service = AgentEnrollmentService(mysql_database, actor="owner@example.com")
    initial = service.create_intent(
        mode=EnrollmentMode.NEW,
        project_uuid=project.public_id,
        device_name="description-device",
        description="Packing line GPU",
        policy=GPUPolicy(),
    )
    first = service.exchange(initial.token.value)
    replacement = service.create_intent(
        mode=EnrollmentMode.REPLACE, replacement_device_uuid=first.device.device_uuid
    )
    second = service.exchange(replacement.token.value)

    assert second.device.id == first.device.id
    assert second.device.description == "Packing line GPU"


def test_enrollment_management_status_is_evidence_driven_and_revocation_is_unused_only(
    mysql_database, identity
):
    from sqlalchemy import select

    from app.db import database_utc
    from app.devices.service import Conflict, GPUPolicy
    from app.enrollment.service import (
        AgentEnrollmentService,
        EnrollmentLifecycle,
        EnrollmentMode,
        EnrollmentRejected,
    )
    from app.models import AgentEnrollment, AuditEvent, Device

    project = identity.create_project("Enrollment lifecycle project")
    service = AgentEnrollmentService(
        mysql_database, actor="owner@example.com", offline_after_seconds=180
    )
    pending = service.create_intent(
        mode=EnrollmentMode.NEW,
        project_uuid=project.public_id,
        device_name="pending-device",
        policy=GPUPolicy(),
    )

    assert service.status(pending.enrollment.public_id).state is EnrollmentLifecycle.PENDING
    revoked = service.revoke_unused(pending.enrollment.public_id)
    assert revoked.state is EnrollmentLifecycle.REVOKED
    with mysql_database.transaction() as session:
        assert (
            session.scalar(
                select(AuditEvent).where(AuditEvent.action == "agent_enrollment.revoked")
            )
            is not None
        )
    with pytest.raises(EnrollmentRejected):
        service.exchange(pending.token.value)

    expired = service.create_intent(
        mode=EnrollmentMode.NEW,
        project_uuid=project.public_id,
        device_name="expired-device",
        policy=GPUPolicy(),
    )
    with mysql_database.transaction() as session:
        row = session.scalar(
            select(AgentEnrollment).where(AgentEnrollment.public_id == expired.enrollment.public_id)
        )
        assert row is not None
        row.expires_at = row.created_at
    assert service.status(expired.enrollment.public_id).state is EnrollmentLifecycle.EXPIRED
    assert expired.enrollment.public_id in {
        item.enrollment_id for item in service.list_to_install()
    }
    deleted = service.delete_unused(expired.enrollment.public_id)
    assert deleted.state is EnrollmentLifecycle.REVOKED
    assert expired.enrollment.public_id not in {
        item.enrollment_id for item in service.list_to_install()
    }
    with pytest.raises(EnrollmentRejected):
        service.exchange(expired.token.value)

    enrolled = service.create_intent(
        mode=EnrollmentMode.NEW,
        project_uuid=project.public_id,
        device_name="enrolled-device",
        policy=GPUPolicy(),
    )
    exchange = service.exchange(enrolled.token.value)
    assert service.status(enrolled.enrollment.public_id).state is EnrollmentLifecycle.ENROLLED
    with pytest.raises(Conflict):
        service.revoke_unused(enrolled.enrollment.public_id)
    with mysql_database.transaction() as session:
        device = session.scalar(select(Device).where(Device.id == exchange.device.id))
        assert device is not None
        device.last_seen_at = database_utc(session)
    assert service.status(enrolled.enrollment.public_id).state is EnrollmentLifecycle.ONLINE
