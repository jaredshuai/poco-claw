"""Tests for message feedback API Actor boundary integration."""

import asyncio
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, TypeVar
from unittest.mock import MagicMock, patch

from app.api.v1.message_feedback import upsert_message_feedback
from app.core.identity import Actor
from app.schemas.message_feedback import MessageFeedbackResponse

T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously for testing.

    Uses asyncio.run() which is the recommended approach for Python 3.12+
    and does not emit deprecation warnings.
    """
    return asyncio.run(coro)


class TestUpsertMessageFeedbackActorBoundary:
    """Tests for upsert_message_feedback Actor boundary."""

    def test_uses_actor_user_id_for_set_feedback_call(self) -> None:
        """Endpoint passes actor.user_id to message_feedback_service.set_feedback."""
        actor = Actor(user_id="actor-user-123")
        mock_db = MagicMock()
        mock_feedback = MagicMock()
        mock_feedback.message_id = 1
        mock_feedback.vote = "like"
        mock_feedback.created_at = datetime(2026, 5, 3, 12, 0, 0)
        mock_feedback.updated_at = datetime(2026, 5, 3, 12, 0, 0)

        with patch(
            "app.api.v1.message_feedback.message_feedback_service.set_feedback",
            return_value=mock_feedback,
        ) as mock_set_feedback:
            _run(
                upsert_message_feedback(
                    message_id=1,
                    request=MagicMock(vote="like"),
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_set_feedback.assert_called_once_with(
            mock_db,
            user_id="actor-user-123",
            message_id=1,
            vote="like",
        )

    def test_passes_message_id_and_vote_unchanged(self) -> None:
        """Endpoint passes message_id and request.vote unchanged to service."""
        actor = Actor(user_id="actor-user-456")
        mock_db = MagicMock()
        mock_feedback = MagicMock()
        mock_feedback.message_id = 42
        mock_feedback.vote = "dislike"
        mock_feedback.created_at = datetime(2026, 5, 3, 12, 0, 0)
        mock_feedback.updated_at = datetime(2026, 5, 3, 12, 0, 0)

        with patch(
            "app.api.v1.message_feedback.message_feedback_service.set_feedback",
            return_value=mock_feedback,
        ) as mock_set_feedback:
            _run(
                upsert_message_feedback(
                    message_id=42,
                    request=MagicMock(vote="dislike"),
                    actor=actor,
                    db=mock_db,
                )
            )

        call_kwargs = mock_set_feedback.call_args
        assert call_kwargs[1]["message_id"] == 42
        assert call_kwargs[1]["vote"] == "dislike"

    def test_response_success_receives_validated_feedback_and_message(self) -> None:
        """Response.success receives MessageFeedbackResponse and exact success message."""
        actor = Actor(user_id="actor-user-789")
        mock_db = MagicMock()
        mock_feedback = MagicMock()
        mock_feedback.message_id = 99
        mock_feedback.vote = "none"
        mock_feedback.created_at = datetime(2026, 5, 3, 14, 30, 0)
        mock_feedback.updated_at = datetime(2026, 5, 3, 14, 30, 0)

        with patch(
            "app.api.v1.message_feedback.message_feedback_service.set_feedback",
            return_value=mock_feedback,
        ):
            with patch("app.api.v1.message_feedback.Response.success") as mock_success:
                _run(
                    upsert_message_feedback(
                        message_id=99,
                        request=MagicMock(vote="none"),
                        actor=actor,
                        db=mock_db,
                    )
                )

        mock_success.assert_called_once()
        call_args = mock_success.call_args
        data_arg = call_args[1]["data"]
        message_arg = call_args[1]["message"]

        assert isinstance(data_arg, MessageFeedbackResponse)
        assert data_arg.message_id == 99
        assert data_arg.vote == "none"
        assert message_arg == "Message feedback saved successfully"
