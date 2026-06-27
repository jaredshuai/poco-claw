import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class OfficeEditSession(Base, TimestampMixin):
    """A short-lived OnlyOffice editing session for a single workspace file.

    Persisted so state survives process restarts; one edit session owns a
    callback token that OnlyOffice uses to authenticate save callbacks.
    """

    __tablename__ = "office_edit_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manifest_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    callback_token: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    discarded: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    # Compatibility alias: callers refer to `.edit_session_id`; maps to the PK.
    @property
    def edit_session_id(self) -> uuid.UUID:
        return self.id
