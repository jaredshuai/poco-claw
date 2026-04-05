from sqlalchemy.orm import Session

from app.models.message_feedback import MessageFeedback


class MessageFeedbackRepository:
    """Data access layer for message feedback records."""

    @staticmethod
    def get_by_user_and_message(
        session_db: Session,
        *,
        user_id: str,
        message_id: int,
    ) -> MessageFeedback | None:
        """Gets the feedback row for a user/message pair."""
        return (
            session_db.query(MessageFeedback)
            .filter(
                MessageFeedback.user_id == user_id,
                MessageFeedback.message_id == message_id,
            )
            .first()
        )

    @staticmethod
    def upsert_vote(
        session_db: Session,
        *,
        user_id: str,
        message_id: int,
        vote: str,
    ) -> MessageFeedback:
        """Creates or updates a feedback row for a user/message pair."""
        feedback = MessageFeedbackRepository.get_by_user_and_message(
            session_db,
            user_id=user_id,
            message_id=message_id,
        )
        if feedback is None:
            feedback = MessageFeedback(
                user_id=user_id,
                message_id=message_id,
                vote=vote,
            )
            session_db.add(feedback)
            return feedback

        feedback.vote = vote
        return feedback

    @staticmethod
    def list_votes_by_user_and_message_ids(
        session_db: Session,
        *,
        user_id: str,
        message_ids: list[int],
    ) -> dict[int, str]:
        """Returns feedback votes keyed by message id."""
        if not message_ids:
            return {}

        rows = (
            session_db.query(MessageFeedback)
            .filter(
                MessageFeedback.user_id == user_id,
                MessageFeedback.message_id.in_(message_ids),
            )
            .all()
        )
        return {row.message_id: row.vote for row in rows}
