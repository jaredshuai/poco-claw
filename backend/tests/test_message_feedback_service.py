import unittest
from unittest.mock import MagicMock, patch

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.message_feedback_service import MessageFeedbackService


class TestMessageFeedbackServiceSetFeedback(unittest.TestCase):
    """Test MessageFeedbackService.set_feedback method."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = MessageFeedbackService()
        self.user_id = "user-123"

    @patch("app.services.message_feedback_service.MessageFeedbackRepository")
    @patch("app.services.message_feedback_service.MessageRepository")
    def test_set_feedback_saves_vote_for_owned_assistant_message(
        self,
        mock_message_repo: MagicMock,
        mock_feedback_repo: MagicMock,
    ) -> None:
        message = MagicMock()
        message.id = 42
        message.role = "assistant"
        mock_message_repo.get_by_id_for_user.return_value = message

        feedback = MagicMock()
        feedback.message_id = 42
        feedback.vote = "like"
        mock_feedback_repo.upsert_vote.return_value = feedback

        result = self.service.set_feedback(
            self.db,
            user_id=self.user_id,
            message_id=42,
            vote="like",
        )

        self.assertEqual(result, feedback)
        mock_message_repo.get_by_id_for_user.assert_called_once_with(
            self.db,
            42,
            self.user_id,
        )
        mock_feedback_repo.upsert_vote.assert_called_once_with(
            self.db,
            user_id=self.user_id,
            message_id=42,
            vote="like",
        )
        self.db.commit.assert_called_once()
        self.db.refresh.assert_called_once_with(feedback)

    @patch("app.services.message_feedback_service.MessageRepository")
    def test_set_feedback_rejects_unknown_or_unowned_message(
        self,
        mock_message_repo: MagicMock,
    ) -> None:
        mock_message_repo.get_by_id_for_user.return_value = None

        with self.assertRaises(AppException) as ctx:
            self.service.set_feedback(
                self.db,
                user_id=self.user_id,
                message_id=42,
                vote="like",
            )

        self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    @patch("app.services.message_feedback_service.MessageRepository")
    def test_set_feedback_rejects_non_assistant_messages(
        self,
        mock_message_repo: MagicMock,
    ) -> None:
        message = MagicMock()
        message.id = 42
        message.role = "user"
        mock_message_repo.get_by_id_for_user.return_value = message

        with self.assertRaises(AppException) as ctx:
            self.service.set_feedback(
                self.db,
                user_id=self.user_id,
                message_id=42,
                vote="dislike",
            )

        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)


if __name__ == "__main__":
    unittest.main()
