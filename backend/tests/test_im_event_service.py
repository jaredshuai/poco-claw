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
