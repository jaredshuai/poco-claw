from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.agent_run import AgentRun
from app.models.agent_session import AgentSession
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.run import RunStatus
from app.schemas.session import SessionStatus
from app.services.clock import Clock, SystemClock
from app.services.run_lifecycle_event_service import RunLifecycleEventService
from app.services.session_queue_service import SessionQueueService


@dataclass(frozen=True, slots=True)
class FinalizeTerminalResult:
    """Result of a finalize_terminal call.

    Attributes:
        session: The database session (db_session), or None if not found.
        promoted_run: The run promoted from queue, if any.
        transition_applied: True if a terminal transition was actually applied,
            False if the run was already terminal or session not found.
    """

    session: AgentSession | None
    promoted_run: AgentRun | None
    transition_applied: bool


class RunLifecycleService:
    TERMINAL_STATUSES = frozenset(
        {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}
    )

    def __init__(
        self,
        clock: Clock | None = None,
        session_queue_service: SessionQueueService | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._session_queue_service = session_queue_service or SessionQueueService()

    def _sync_scheduled_task_last_status(self, db: Session, db_run: AgentRun) -> None:
        if not db_run.scheduled_task_id:
            return

        db_task = ScheduledTaskRepository.get_by_id(db, db_run.scheduled_task_id)
        if not db_task:
            return

        if db_task.last_run_id and db_task.last_run_id != db_run.id:
            return

        db_task.last_run_id = db_run.id
        db_task.last_run_status = db_run.status

        if db_run.status == RunStatus.FAILED:
            db_task.last_error = db_run.last_error or db_task.last_error
        elif db_run.status in {RunStatus.COMPLETED, RunStatus.CANCELED}:
            db_task.last_error = None

    def mark_running(
        self, db: Session, db_run: AgentRun, lease_seconds: int | None = None
    ) -> AgentSession | None:
        db_session = SessionRepository.get_by_id_for_update(db, db_run.session_id)
        if not db_session:
            return None

        if db_run.status in self.TERMINAL_STATUSES:
            return db_session

        now = self._clock.now_utc()
        if db_run.status in {RunStatus.QUEUED, RunStatus.CLAIMED}:
            self._session_queue_service.clear_execution_state(db_session)
            db_run.status = RunStatus.RUNNING
        if db_run.started_at is None:
            db_run.started_at = now

        # Set lease expiration if duration provided; otherwise preserve existing lease
        if lease_seconds is not None and lease_seconds > 0:
            db_run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        # If no lease_seconds provided and run already has a lease, preserve it
        # (this allows callback-driven mark_running to keep existing running lease)

        if db_session.status != SessionStatus.CANCELED:
            db_session.status = SessionStatus.RUNNING

        self._sync_scheduled_task_last_status(db, db_run)
        db.flush()
        return db_session

    def finalize_terminal(
        self,
        db: Session,
        db_run: AgentRun,
        *,
        status: str,
        error_message: str | None = None,
    ) -> FinalizeTerminalResult:
        db_session = SessionRepository.get_by_id_for_update(db, db_run.session_id)
        if not db_session:
            return FinalizeTerminalResult(
                session=None,
                promoted_run=None,
                transition_applied=False,
            )

        if db_run.status in self.TERMINAL_STATUSES:
            if status == RunStatus.FAILED and error_message and not db_run.last_error:
                db_run.last_error = error_message
            self._sync_scheduled_task_last_status(db, db_run)
            db.flush()
            return FinalizeTerminalResult(
                session=db_session,
                promoted_run=None,
                transition_applied=False,
            )

        # --- Status-only hard guards (no worker_id needed) ---
        now = self._clock.now_utc()
        from_status = db_run.status

        if status == RunStatus.COMPLETED and from_status != RunStatus.RUNNING:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=(
                    f"Run cannot be completed from status '{from_status}'; "
                    f"only 'running' runs can complete"
                ),
            )

        if status == RunStatus.FAILED and from_status not in [
            RunStatus.CLAIMED,
            RunStatus.RUNNING,
        ]:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=(
                    f"Run cannot be failed from status '{from_status}'; "
                    f"only 'claimed' or 'running' runs can fail"
                ),
            )

        if status == RunStatus.CANCELED and from_status not in [
            RunStatus.QUEUED,
            RunStatus.CLAIMED,
            RunStatus.RUNNING,
        ]:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=(
                    f"Run cannot be canceled from status '{from_status}'; "
                    f"only 'queued', 'claimed', or 'running' runs can cancel"
                ),
            )

        # --- Record lifecycle event ---
        event_service = RunLifecycleEventService()
        event_service.record_event(
            db,
            run_id=db_run.id,
            session_id=db_run.session_id,
            event_type="status_transition",
            event_source="run_lifecycle_service",
            from_status=from_status,
            to_status=status,
            claimed_by=db_run.claimed_by,
            context={
                "error_message": error_message,
            },
        )

        db_run.status = status
        if db_run.finished_at is None:
            db_run.finished_at = now
        db_run.lease_expires_at = None

        promoted_run: AgentRun | None = None
        if status == RunStatus.COMPLETED:
            db_run.progress = 100
            db_run.last_error = None
            promoted_run = self._session_queue_service.promote_next_if_available(
                db, db_session
            )
            if promoted_run is None:
                db_session.status = SessionStatus.COMPLETED
        elif status == RunStatus.FAILED:
            if error_message:
                db_run.last_error = error_message
            self._session_queue_service.pause_active_items(db, db_session.id)
            db_session.status = SessionStatus.FAILED
        elif status == RunStatus.CANCELED:
            self._session_queue_service.cancel_active_items(db, db_session.id)
            db_session.status = SessionStatus.CANCELED

        self._sync_scheduled_task_last_status(db, db_run)
        db.flush()
        return FinalizeTerminalResult(
            session=db_session,
            promoted_run=promoted_run,
            transition_applied=True,
        )
