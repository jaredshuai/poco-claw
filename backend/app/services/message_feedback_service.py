from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.repositories.message_feedback_repository import MessageFeedbackRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message_feedback import MessageFeedbackVote


class MessageFeedbackService:
    """Service layer for message feedback persistence."""

    def set_feedback(
        self,
        db: Session,
        *,
        user_id: str,
        message_id: int,
        vote: MessageFeedbackVote,
    ):
        """Persists the feedback vote for an owned assistant message."""
        message = MessageRepository.get_by_id_for_user(db, message_id, user_id)
        if message is None:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Message not found: {message_id}",
            )
        if message.role != "assistant":
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Feedback is only supported for assistant messages",
            )

        feedback = MessageFeedbackRepository.upsert_vote(
            db,
            user_id=user_id,
            message_id=message_id,
            vote=vote,
        )
        db.commit()
        db.refresh(feedback)
        return feedback
