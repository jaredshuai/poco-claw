"""Tests for User Input Requests API Actor boundary.

These tests verify the HTTP adapter boundary correctly:
- Uses Actor.user_id when calling the service
- Passes session_id unchanged
- Passes str(request_id) conversion unchanged
- Passes the request object unchanged
- Returns the expected success messages
"""

import json
import uuid
from contextlib import contextmanager
from typing import Any, Coroutine, Generator, TypeVar
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.api.v1.user_input_requests import (
    answer_user_input_request,
    list_pending_user_input_requests,
)
from app.core.identity import Actor
from app.schemas.user_input_request import UserInputAnswerRequest

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
def _mock_service(result: Any = None) -> Generator[MagicMock, None, None]:
    """Context manager to mock the user_input_service."""
    with patch("app.api.v1.user_input_requests.user_input_service") as mock_service:
        mock_service.list_pending_for_user.return_value = result
        mock_service.answer_request.return_value = result
        yield mock_service


class TestListPendingUserInputRequestsActorBoundary:
    """Tests for list_pending_user_input_requests endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to the service."""
        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock(spec=Session)
        expected_result = []

        with _mock_service(expected_result) as mock_service:
            response = _run(
                list_pending_user_input_requests(
                    actor=actor,
                    session_id=None,
                    db=mock_db,
                )
            )

        mock_service.list_pending_for_user.assert_called_once()
        call_args = mock_service.list_pending_for_user.call_args
        assert call_args[1]["user_id"] == "test-user-123"
        assert response.status_code == 200

    def test_passes_session_id_unchanged(self) -> None:
        """Verify session_id is passed unchanged to the service."""
        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock(spec=Session)
        test_session_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

        with _mock_service() as mock_service:
            _run(
                list_pending_user_input_requests(
                    actor=actor,
                    session_id=test_session_id,
                    db=mock_db,
                )
            )

        call_args = mock_service.list_pending_for_user.call_args
        assert call_args[1]["session_id"] == test_session_id

    def test_passes_session_id_none(self) -> None:
        """Verify None session_id is passed correctly."""
        actor = Actor(user_id="test-user-789", auth_source="test")
        mock_db = MagicMock(spec=Session)

        with _mock_service() as mock_service:
            _run(
                list_pending_user_input_requests(
                    actor=actor,
                    session_id=None,
                    db=mock_db,
                )
            )

        call_args = mock_service.list_pending_for_user.call_args
        assert call_args[1]["session_id"] is None

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock(spec=Session)
        expected_result = []

        with _mock_service(expected_result):
            response = _run(
                list_pending_user_input_requests(
                    actor=actor,
                    session_id=None,
                    db=mock_db,
                )
            )

        body = json.loads(bytes(response.body))
        assert body["message"] == "User input requests retrieved"
        assert body["data"] == expected_result


class TestAnswerUserInputRequestActorBoundary:
    """Tests for answer_user_input_request endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to the service."""
        actor = Actor(user_id="answer-user-123", auth_source="test")
        mock_db = MagicMock(spec=Session)
        request_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        answer_request = UserInputAnswerRequest(answers={"key": "value"})
        expected_result = MagicMock()

        with _mock_service(expected_result) as mock_service:
            response = _run(
                answer_user_input_request(
                    request_id=request_id,
                    request=answer_request,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_service.answer_request.assert_called_once()
        call_args = mock_service.answer_request.call_args
        assert call_args[1]["user_id"] == "answer-user-123"
        assert response.status_code == 200

    def test_passes_str_request_id(self) -> None:
        """Verify request_id is converted to str via str(request_id)."""
        actor = Actor(user_id="answer-user-456", auth_source="test")
        mock_db = MagicMock(spec=Session)
        request_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        answer_request = UserInputAnswerRequest(answers={"foo": "bar"})

        with _mock_service() as mock_service:
            _run(
                answer_user_input_request(
                    request_id=request_id,
                    request=answer_request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.answer_request.call_args
        assert call_args[1]["request_id"] == str(request_id)
        assert call_args[1]["request_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    def test_passes_request_object_unchanged(self) -> None:
        """Verify the request object is passed unchanged to the service."""
        actor = Actor(user_id="answer-user-789", auth_source="test")
        mock_db = MagicMock(spec=Session)
        request_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        answer_request = UserInputAnswerRequest(answers={"field": "response"})

        with _mock_service() as mock_service:
            _run(
                answer_user_input_request(
                    request_id=request_id,
                    request=answer_request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.answer_request.call_args
        # The request object should be passed as answer_request keyword arg
        assert call_args[1]["answer_request"] is answer_request

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message."""
        actor = Actor(user_id="answer-user-msg", auth_source="test")
        mock_db = MagicMock(spec=Session)
        request_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        answer_request = UserInputAnswerRequest(answers={"x": "y"})
        expected_result = MagicMock()

        with _mock_service(expected_result):
            response = _run(
                answer_user_input_request(
                    request_id=request_id,
                    request=answer_request,
                    actor=actor,
                    db=mock_db,
                )
            )

        body = json.loads(bytes(response.body))
        assert body["message"] == "User input request answered"
