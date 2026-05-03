"""Tests for Tasks API Actor boundary.

These tests verify the HTTP adapter boundary correctly:
- Uses Actor.user_id when calling TaskService.enqueue_task
- Passes the request object unchanged
- Adds title background task only for new session (request.session_id is None)
- Passes result.session_id and request.prompt unchanged to title task
- Returns the expected success message
"""

import uuid
from contextlib import contextmanager
from typing import Any, Coroutine, Generator, TypeVar
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.api.v1.tasks import enqueue_task
from app.core.identity import Actor
from app.schemas.task import TaskEnqueueRequest, TaskEnqueueResponse

T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Execute a coroutine synchronously without asyncio deprecation warnings."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@contextmanager
def _mock_task_service(
    result: Any = None,
) -> Generator[MagicMock, None, None]:
    """Context manager to mock the task_service."""
    with patch("app.api.v1.tasks.task_service") as mock_service:
        mock_service.enqueue_task.return_value = result
        yield mock_service


@contextmanager
def _mock_response_success() -> Generator[MagicMock, None, None]:
    """Context manager to mock Response.success."""
    with patch("app.api.v1.tasks.Response.success") as mock_success:
        mock_success.return_value = MagicMock(status_code=200, body=b'{"data":{}}')
        yield mock_success


class TestEnqueueTaskActorBoundary:
    """Tests for enqueue_task endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to TaskService.enqueue_task."""
        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_bg = MagicMock(spec=BackgroundTasks)
        request = TaskEnqueueRequest(prompt="Hello")
        session_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = TaskEnqueueResponse(session_id=session_id, status="pending")

        with _mock_task_service(result):
            _run(
                enqueue_task(
                    request=request,
                    background_tasks=mock_bg,
                    actor=actor,
                    db=mock_db,
                )
            )

        with _mock_task_service(result) as mock_service:
            _run(
                enqueue_task(
                    request=request,
                    background_tasks=mock_bg,
                    actor=actor,
                    db=mock_db,
                )
            )
            call_args = mock_service.enqueue_task.call_args
            assert call_args[0][1] == "test-user-123"

    def test_passes_request_object_unchanged(self) -> None:
        """Verify the request object is passed unchanged to TaskService.enqueue_task."""
        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_bg = MagicMock(spec=BackgroundTasks)
        request = TaskEnqueueRequest(
            prompt="Test prompt",
            session_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        )
        session_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        result = TaskEnqueueResponse(session_id=session_id, status="pending")

        with _mock_task_service(result) as mock_service:
            _run(
                enqueue_task(
                    request=request,
                    background_tasks=mock_bg,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.enqueue_task.call_args
        assert call_args[0][2] is request

    def test_title_task_added_for_new_session(self) -> None:
        """Verify title background task is added when request.session_id is None."""
        actor = Actor(user_id="test-user-789", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_bg = MagicMock(spec=BackgroundTasks)
        request = TaskEnqueueRequest(prompt="New session prompt", session_id=None)
        session_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        result = TaskEnqueueResponse(session_id=session_id, status="pending")

        with _mock_task_service(result):
            _run(
                enqueue_task(
                    request=request,
                    background_tasks=mock_bg,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_bg.add_task.assert_called_once()
        call_args = mock_bg.add_task.call_args
        assert call_args[0][0].__name__ == "generate_and_update"
        assert call_args[0][1] == session_id
        assert call_args[0][2] == "New session prompt"

    def test_title_task_not_added_for_existing_session(self) -> None:
        """Verify title background task is NOT added when request.session_id is set."""
        actor = Actor(user_id="test-user-existing", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_bg = MagicMock(spec=BackgroundTasks)
        existing_session_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        request = TaskEnqueueRequest(
            prompt="Existing session", session_id=existing_session_id
        )
        result = TaskEnqueueResponse(session_id=existing_session_id, status="pending")

        with _mock_task_service(result):
            _run(
                enqueue_task(
                    request=request,
                    background_tasks=mock_bg,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_bg.add_task.assert_not_called()

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_bg = MagicMock(spec=BackgroundTasks)
        request = TaskEnqueueRequest(prompt="Message test")
        session_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        result = TaskEnqueueResponse(session_id=session_id, status="pending")

        with _mock_task_service(result):
            with _mock_response_success() as mock_success:
                _run(
                    enqueue_task(
                        request=request,
                        background_tasks=mock_bg,
                        actor=actor,
                        db=mock_db,
                    )
                )

        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "Task enqueued successfully"
        assert call_kwargs["data"] is result
