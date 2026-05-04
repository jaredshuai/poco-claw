"""Service for recording run lifecycle audit events."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_run_lifecycle_event import AgentRunLifecycleEvent


class RunLifecycleEventService:
    """Service for recording run lifecycle audit events."""

    def record_event(
        self,
        db: Session,
        *,
        run_id: uuid.UUID,
        session_id: uuid.UUID,
        event_type: str,
        event_source: str,
        from_status: str | None = None,
        to_status: str | None = None,
        worker_id: str | None = None,
        claimed_by: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentRunLifecycleEvent:
        """Record a run lifecycle audit event.

        Args:
            db: Database session.
            run_id: The run ID.
            session_id: The session ID.
            event_type: Type of event (e.g., "stale_callback_ignored",
                "duplicate_terminal_ignored").
            event_source: Source of the event (e.g., "callback_service").
            from_status: Previous status if applicable.
            to_status: Target status if applicable.
            worker_id: Worker ID from the callback.
            claimed_by: Current claimed_by value on the run.
            context: Additional context as JSON.

        Returns:
            The created event record.
        """
        event = AgentRunLifecycleEvent(
            run_id=run_id,
            session_id=session_id,
            event_type=event_type,
            event_source=event_source,
            from_status=from_status,
            to_status=to_status,
            worker_id=worker_id,
            claimed_by=claimed_by,
            context=context,
        )
        db.add(event)
        return event
