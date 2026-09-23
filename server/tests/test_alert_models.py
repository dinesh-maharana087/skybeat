from app.models import AlertEvent, Device, Incident, NotificationAttempt, NotificationDelivery


def test_stage03_models_preserve_incident_event_and_delivery_history():
    assert Incident.__tablename__ == "incidents"
    assert AlertEvent.__tablename__ == "alert_events"
    assert NotificationDelivery.__tablename__ == "notification_deliveries"
    assert NotificationAttempt.__tablename__ == "notification_attempts"
    assert "availability_state" in Device.__table__.c
    assert "active_key" in Incident.__table__.c
    assert "recipient_key" in NotificationDelivery.__table__.c
    assert "attempt_no" in NotificationAttempt.__table__.c
