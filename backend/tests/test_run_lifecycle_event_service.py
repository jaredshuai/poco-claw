import uuid
from unittest.mock import MagicMock

from app.services.run_lifecycle_event_service import RunLifecycleEventService


def test_record_event_adds_lifecycle_event_to_session() -> None:
    db = MagicMock()
    service = RunLifecycleEventService()

    event = service.record_event(
        db,
        run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        event_type="stale_callback_ignored",
        event_source="callback_service",
        from_status="running",
        to_status="completed",
        worker_id="worker-a",
        claimed_by="worker-b",
        context={"callback_status": "completed"},
    )

    db.add.assert_called_once_with(event)
    assert event.event_type == "stale_callback_ignored"
    assert event.event_source == "callback_service"
    assert event.from_status == "running"
    assert event.to_status == "completed"
    assert event.worker_id == "worker-a"
    assert event.claimed_by == "worker-b"
    assert event.context == {"callback_status": "completed"}
