import pytest


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
    from app.models import AgentEnrollment

    columns = AgentEnrollment.__table__.c

    assert {"public_id", "enrollment_digest", "verification_digest", "expires_at"} <= set(
        columns.keys()
    )
    assert columns.enrollment_digest.unique
    assert columns.verification_digest.unique
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
        policy=GPUPolicy(),
    )

    exchanged = service.exchange(intent.token.value)

    assert exchanged.device.name == "enrollment-service-device"
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
