from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.agent_message import AgentMessage


class MessageFeedback(Base, TimestampMixin):
    __tablename__ = "message_feedbacks"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_message_feedback_user_msg"),
        CheckConstraint(
            "vote IN ('like', 'dislike', 'none')",
            name="ck_message_feedback_vote",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vote: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        server_default=text("'none'"),
    )

    message: Mapped["AgentMessage"] = relationship(back_populates="feedback_entries")
