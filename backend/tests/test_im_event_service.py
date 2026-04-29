from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.agent_session import AgentSession
from app.models.user_input_request import UserInputRequest


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


def test_user_input_request_created_event_uses_service_clock_when_created_at_missing():
    from app.services.im import ImEventService

    now = datetime(2025, 2, 15, 10, 30, tzinfo=UTC)
    db_session = cast(
        AgentSession,
        SimpleNamespace(
            id="session-1",
            user_id="user-1",
            title="Session title",
            status="waiting",
        ),
    )
    request = cast(
        UserInputRequest,
        SimpleNamespace(
            id=uuid4(),
            tool_name="ask_user",
            tool_input={"question": "Proceed?"},
            status="pending",
            expires_at=now + timedelta(minutes=5),
            answered_at=None,
            created_at=None,
        ),
    )
    service = ImEventService(clock=FixedClock(now))

    with patch("app.services.im.ImEventOutboxRepository.create_if_absent") as create:
        service.enqueue_user_input_request_created(
            cast(Session, MagicMock()),
            db_session=db_session,
            request=request,
        )

    payload = create.call_args.kwargs["payload"]
    occurred_at = datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
    assert occurred_at == now


def test_user_input_request_created_event_uses_injected_id_generator():
    from app.services.im import ImEventService

    now = datetime(2025, 2, 15, 10, 30, tzinfo=UTC)
    db_session = cast(
        AgentSession,
        SimpleNamespace(
            id="session-1",
            user_id="user-1",
            title="Session title",
            status="waiting",
        ),
    )
    request = cast(
        UserInputRequest,
        SimpleNamespace(
            id=uuid4(),
            tool_name="ask_user",
            tool_input={"question": "Proceed?"},
            status="pending",
            expires_at=now + timedelta(minutes=5),
            answered_at=None,
            created_at=now,
        ),
    )
    service = ImEventService(
        clock=FixedClock(now),
        id_generator=FixedIdGenerator("event-fixed"),
    )

    with patch("app.services.im.ImEventOutboxRepository.create_if_absent") as create:
        service.enqueue_user_input_request_created(
            cast(Session, MagicMock()),
            db_session=db_session,
            request=request,
        )

    assert create.call_args.kwargs["payload"]["id"] == "event-fixed"


def test_command_service_uses_injected_backend_factory_without_constructing_default_backend():
    from app.services.im import CommandService

    backend = MagicMock()

    with patch(
        "app.services.im.BackendClient",
        side_effect=AssertionError("backend client should be provided by factory"),
    ):
        service = CommandService(backend_client_factory=lambda: backend)

    assert service.backend is backend


def test_dispatcher_mark_delivered_passes_clock_to_repository():
    from app.services.im import ImEventDispatcher

    now = datetime(2025, 2, 15, 10, 30, tzinfo=UTC)
    dispatcher = ImEventDispatcher(clock=FixedClock(now))
    db = MagicMock()

    with (
        patch("app.services.im.SessionLocal", return_value=db),
        patch("app.services.im.ImEventOutboxRepository.mark_delivered") as mark,
    ):
        dispatcher._mark_delivered("event-1")

    mark.assert_called_once_with(db, event_id="event-1", now_utc=now)
    db.commit.assert_called_once_with()


def test_dispatcher_mark_retry_passes_clock_to_repository():
    from app.services.im import ImEventDispatcher

    now = datetime(2025, 2, 15, 10, 30, tzinfo=UTC)
    dispatcher = ImEventDispatcher(clock=FixedClock(now))
    db = MagicMock()

    with (
        patch("app.services.im.SessionLocal", return_value=db),
        patch("app.services.im.ImEventOutboxRepository.mark_retry") as mark,
    ):
        dispatcher._mark_retry("event-1", "boom", 3.5)

    mark.assert_called_once_with(
        db,
        event_id="event-1",
        error_message="boom",
        delay_seconds=3.5,
        now_utc=now,
    )
    db.commit.assert_called_once_with()


def test_dispatcher_claim_due_batch_passes_clock_to_repository():
    from app.services.im import ImEventDispatcher

    now = datetime(2025, 2, 15, 10, 30, tzinfo=UTC)
    dispatcher = ImEventDispatcher(clock=FixedClock(now))
    db = MagicMock()

    with (
        patch("app.services.im.SessionLocal", return_value=db),
        patch(
            "app.services.im.ImEventOutboxRepository.claim_due_batch",
            return_value=[],
        ) as claim,
    ):
        result = dispatcher._claim_due_batch(10, 30)

    assert result == []
    claim.assert_called_once_with(
        db,
        limit=10,
        lease_seconds=30,
        now_utc=now,
    )
    db.commit.assert_called_once_with()
