import unittest
from unittest.mock import MagicMock

from app.models.message_feedback import MessageFeedback
from app.repositories.message_feedback_repository import MessageFeedbackRepository


class TestMessageFeedbackRepositoryUpsertVote(unittest.TestCase):
    """Test MessageFeedbackRepository.upsert_vote method."""

    def test_upsert_vote_creates_feedback_when_missing(self) -> None:
        db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None

        result = MessageFeedbackRepository.upsert_vote(
            db,
            user_id="user-123",
            message_id=42,
            vote="like",
        )

        self.assertIsInstance(result, MessageFeedback)
        self.assertEqual(result.user_id, "user-123")
        self.assertEqual(result.message_id, 42)
        self.assertEqual(result.vote, "like")
        db.add.assert_called_once_with(result)

    def test_upsert_vote_updates_existing_feedback(self) -> None:
        db = MagicMock()
        existing = MagicMock(spec=MessageFeedback)
        existing.user_id = "user-123"
        existing.message_id = 42
        existing.vote = "like"

        mock_query = MagicMock()
        mock_filter = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = existing

        result = MessageFeedbackRepository.upsert_vote(
            db,
            user_id="user-123",
            message_id=42,
            vote="none",
        )

        self.assertEqual(result, existing)
        self.assertEqual(existing.vote, "none")
        db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
