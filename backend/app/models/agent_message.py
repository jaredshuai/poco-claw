import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.agent_session import AgentSession
    from app.models.message_feedback import MessageFeedback
    from app.models.tool_execution import ToolExecution


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"
    __table_args__ = (
        Index(
            "ix_agent_messages_session_id_created_at_id",
            "session_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped["AgentSession"] = relationship(back_populates="messages")
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        foreign_keys="ToolExecution.message_id",
    )
    tool_result_executions: Mapped[list["ToolExecution"]] = relationship(
        back_populates="result_message",
        foreign_keys="ToolExecution.result_message_id",
    )
    feedback_entries: Mapped[list["MessageFeedback"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
