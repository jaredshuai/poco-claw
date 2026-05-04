import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class AgentRunLifecycleEvent(Base, TimestampMixin):
    """Audit events for run lifecycle decisions, especially ignored callbacks.

    Records when callbacks are ignored due to stale worker ownership or
    duplicate terminal transitions, making these decisions queryable and
    auditable per the clean architecture target.
    """

    __tablename__ = "agent_run_lifecycle_events"
    __table_args__ = (
        Index("ix_lifecycle_events_run_id", "run_id"),
        Index("ix_lifecycle_events_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_source: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
