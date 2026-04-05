import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.message_service import MessageService


def create_mock_message(message_id: int = 1) -> MagicMock:
    mock = MagicMock()
    mock.id = message_id
    mock.session_id = uuid.uuid4()
    mock.role = "assistant"
    mock.content = {"text": "Hello"}
    mock.text_preview = "Hello"
    mock.created_at = datetime.now(timezone.utc)
    mock.updated_at = datetime.now(timezone.utc)
    return mock


class TestMessageServiceBuildMessageResponses(unittest.TestCase):
    """Test feedback vote exposure in message responses."""

    @patch("app.services.message_service.MessageFeedbackRepository")
    def test_build_message_responses_includes_feedback_vote(
        self,
        mock_feedback_repo: MagicMock,
    ) -> None:
        db = MagicMock()
        message = create_mock_message(message_id=7)
        mock_feedback_repo.list_votes_by_user_and_message_ids.return_value = {7: "like"}

        service = MessageService()
        responses = service._build_message_responses(
            db,
            [message],
            user_id="user-123",
        )

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].feedback_vote, "like")

    @patch("app.services.message_service.MessageFeedbackRepository")
    def test_build_message_responses_defaults_feedback_vote_to_none(
        self,
        mock_feedback_repo: MagicMock,
    ) -> None:
        db = MagicMock()
        message = create_mock_message(message_id=9)
        mock_feedback_repo.list_votes_by_user_and_message_ids.return_value = {}

        service = MessageService()
        responses = service._build_message_responses(
            db,
            [message],
            user_id="user-123",
        )

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].feedback_vote, "none")


if __name__ == "__main__":
    unittest.main()
