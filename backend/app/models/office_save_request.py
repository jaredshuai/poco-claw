import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class OfficeSaveRequest(Base, TimestampMixin):
    """A single force-save lifecycle row for an OnlyOffice edit session.

    Tracks the save state machine: pending -> saving -> callback_received ->
    staged -> saved (or failed at any step). ``staged_object_key`` doubles as
    the recovery marker for crash-safe writeback completion.
    """

    __tablename__ = "office_save_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    edit_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("office_edit_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_key: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staged_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Compatibility alias: callers refer to `.save_request_id`; maps to the PK.
    if not TYPE_CHECKING:

        @property
        def save_request_id(self) -> uuid.UUID:
            return self.id
