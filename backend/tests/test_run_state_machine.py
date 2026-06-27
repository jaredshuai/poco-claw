"""Tests for Run state machine — transition policy, lifecycle service, and repository.

These tests nail down the current behavior before adding new guards in Step 2/3.
Uses the same unittest + MagicMock pattern as test_run_service.py and test_run_lifecycle_service.py.
"""

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.run_transition_policy import (
    RUN_TRANSITION_APPLY,
    RUN_TRANSITION_NOOP,
    RunTransitionPolicy,
)
from app.services.run_lifecycle_service import (
    FinalizeTerminalResult,
    RunLifecycleService,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


def create_mock_run(
    run_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    status: str = "queued",
    claimed_by: str | None = None,
    started_at: datetime | None = None,
    lease_expires_at: datetime | None = None,
    user_message_id: int = 1,
) -> MagicMock:
    """Create a properly initialized mock run object."""
    mock_run = MagicMock()
    mock_run.id = run_id or uuid.uuid4()
    mock_run.run_id = mock_run.id
    mock_run.session_id = session_id or uuid.uuid4()
    mock_run.user_message_id = user_message_id
    mock_run.status = status
    mock_run.permission_mode = "default"
    mock_run.progress = 0
    mock_run.schedule_mode = "immediate"
    mock_run.scheduled_task_id = None
    mock_run.scheduled_at = datetime.now(timezone.utc)
    mock_run.config_snapshot = {}
    mock_run.claimed_by = claimed_by
    mock_run.lease_expires_at = lease_expires_at
    mock_run.attempts = 0
    mock_run.last_error = None
    mock_run.started_at = started_at
    mock_run.finished_at = None
    mock_run.created_at = datetime.now(timezone.utc)
    mock_run.updated_at = datetime.now(timezone.utc)
    mock_run.usage = None
    return mock_run


def future_lease() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=5)


def expired_lease() -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=1)


# =============================================================================
# RunTransitionPolicy Tests
# =============================================================================


class TestRunTransitionPolicyEvaluateStart(unittest.TestCase):
    """RunTransitionPolicy.evaluate_start — claimed->running, terminal->noop, others->error."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)

    # --- Terminal statuses → noop ---

    def test_completed_returns_noop(self) -> None:
        run = create_mock_run(status="completed")
        result = RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    def test_failed_returns_noop(self) -> None:
        run = create_mock_run(status="failed")
        result = RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    def test_canceled_returns_noop(self) -> None:
        run = create_mock_run(status="canceled")
        result = RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    # --- Running → noop (with worker ownership check) ---

    def test_running_same_worker_returns_noop(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-1")
        result = RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    def test_running_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-2")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_running_no_owner_raises_forbidden(self) -> None:
        run = create_mock_run(status="running", claimed_by=None)
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    # --- Claimed → apply (with worker + lease checks) ---

    def test_claimed_same_worker_active_lease_returns_apply(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-1",
            lease_expires_at=future_lease(),
        )
        result = RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    def test_claimed_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-2",
            lease_expires_at=future_lease(),
        )
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_claimed_expired_lease_raises_forbidden(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-1",
            lease_expires_at=self.now - timedelta(seconds=1),
        )
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_claimed_no_lease_raises_forbidden(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-1",
            lease_expires_at=None,
        )
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    # --- Queued → bad request (can't start an unclaimed run) ---

    def test_queued_raises_bad_request(self) -> None:
        run = create_mock_run(status="queued")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_unknown_status_raises_bad_request(self) -> None:
        run = create_mock_run(status="unknown")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_start(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)


class TestRunTransitionPolicyEvaluateFail(unittest.TestCase):
    """RunTransitionPolicy.evaluate_fail — claimed/running->apply, terminal->noop, others->error."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)

    # --- Terminal statuses → noop ---

    def test_completed_returns_noop(self) -> None:
        run = create_mock_run(status="completed")
        result = RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    def test_failed_returns_noop(self) -> None:
        run = create_mock_run(status="failed")
        result = RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    def test_canceled_returns_noop(self) -> None:
        run = create_mock_run(status="canceled")
        result = RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_NOOP)

    # --- Running → apply (worker ownership, no lease check needed) ---

    def test_running_same_worker_returns_apply(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-1")
        result = RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    def test_running_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-2")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    # --- Claimed → apply (worker + lease check) ---

    def test_claimed_same_worker_active_lease_returns_apply(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-1",
            lease_expires_at=future_lease(),
        )
        result = RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    def test_claimed_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-2",
            lease_expires_at=future_lease(),
        )
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_claimed_expired_lease_raises_forbidden(self) -> None:
        run = create_mock_run(
            status="claimed",
            claimed_by="worker-1",
            lease_expires_at=self.now - timedelta(seconds=1),
        )
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    # --- Queued → bad request ---

    def test_queued_raises_bad_request(self) -> None:
        run = create_mock_run(status="queued")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_unknown_status_raises_bad_request(self) -> None:
        run = create_mock_run(status="unknown")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_fail(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)


class TestRunTransitionPolicyEvaluateComplete(unittest.TestCase):
    """RunTransitionPolicy.evaluate_complete — only running->completed, others blocked."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)

    def test_running_same_worker_returns_apply(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-1")
        result = RunTransitionPolicy.evaluate_complete(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    def test_running_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-2")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_complete(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_running_no_owner_raises_forbidden(self) -> None:
        run = create_mock_run(status="running", claimed_by=None)
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_complete(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    # --- Terminal → noop ---

    def test_terminal_returns_noop(self) -> None:
        for status in ["completed", "failed", "canceled"]:
            run = create_mock_run(status=status)
            result = RunTransitionPolicy.evaluate_complete(
                run, "worker-1", now=self.now
            )
            self.assertEqual(result, RUN_TRANSITION_NOOP)

    # --- Non-running, non-terminal → bad request ---

    def test_queued_raises_bad_request(self) -> None:
        run = create_mock_run(status="queued")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_complete(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_claimed_raises_bad_request(self) -> None:
        run = create_mock_run(status="claimed")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_complete(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_unknown_status_raises_bad_request(self) -> None:
        run = create_mock_run(status="unknown")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_complete(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)


class TestRunTransitionPolicyEvaluateCancel(unittest.TestCase):
    """RunTransitionPolicy.evaluate_cancel — queued/claimed/running->canceled, others blocked."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)

    # --- Non-terminal, valid statuses → apply ---

    def test_queued_returns_apply(self) -> None:
        """queued runs have no claimed_by, so no worker ownership check."""
        run = create_mock_run(status="queued", claimed_by=None)
        result = RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    def test_claimed_same_worker_returns_apply(self) -> None:
        run = create_mock_run(status="claimed", claimed_by="worker-1")
        result = RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    def test_running_same_worker_returns_apply(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-1")
        result = RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
        self.assertEqual(result, RUN_TRANSITION_APPLY)

    # --- Worker ownership check for claimed/running ---

    def test_claimed_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(status="claimed", claimed_by="worker-2")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_running_different_worker_raises_forbidden(self) -> None:
        run = create_mock_run(status="running", claimed_by="worker-2")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    # --- Terminal → noop ---

    def test_terminal_returns_noop(self) -> None:
        for status in ["completed", "failed", "canceled"]:
            run = create_mock_run(status=status)
            result = RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
            self.assertEqual(result, RUN_TRANSITION_NOOP)

    # --- Unknown status → bad request ---

    def test_unknown_status_raises_bad_request(self) -> None:
        run = create_mock_run(status="unknown")
        with self.assertRaises(AppException) as ctx:
            RunTransitionPolicy.evaluate_cancel(run, "worker-1", now=self.now)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)


# =============================================================================
# RunLifecycleService Tests
# =============================================================================


class TestRunLifecycleServiceMarkRunning(unittest.TestCase):
    """RunLifecycleService.mark_running — status transitions and lease handling."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        self.queue_service = MagicMock()
        self.service = RunLifecycleService(
            clock=FixedClock(self.now),
            session_queue_service=self.queue_service,
        )
        self.db = MagicMock()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_session_not_found(self, mock_repo: MagicMock) -> None:
        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        mock_repo.get_by_id_for_update.return_value = None

        result = self.service.mark_running(self.db, db_run)

        self.assertIsNone(result)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_terminal_status_unchanged(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        db_session.status = "completed"
        mock_repo.get_by_id_for_update.return_value = db_session

        for terminal_status in ["completed", "failed", "canceled"]:
            db_run = MagicMock()
            db_run.session_id = uuid.uuid4()
            db_run.status = terminal_status

            result = self.service.mark_running(self.db, db_run)

            self.assertEqual(result, db_session)
            # Status should not change
            self.assertEqual(db_run.status, terminal_status)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_queued_to_running(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        db_session.status = "pending"
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "queued"
        db_run.started_at = None

        self.service.mark_running(self.db, db_run)

        self.assertEqual(db_run.status, "running")
        self.assertEqual(db_run.started_at, self.now)
        self.queue_service.clear_execution_state.assert_called_once_with(db_session)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_claimed_to_running(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        db_session.status = "pending"
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "claimed"
        db_run.started_at = None

        self.service.mark_running(self.db, db_run)

        self.assertEqual(db_run.status, "running")
        self.assertEqual(db_run.started_at, self.now)
        self.queue_service.clear_execution_state.assert_called_once()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_running_preserves_started_at(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        db_session.status = "running"
        mock_repo.get_by_id_for_update.return_value = db_session

        original_started_at = self.now - timedelta(hours=1)
        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.started_at = original_started_at

        self.service.mark_running(self.db, db_run)

        # started_at should NOT be overwritten (already set)
        self.assertEqual(db_run.started_at, original_started_at)

    # --- Lease handling ---

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_sets_lease_when_provided(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        db_session.status = "pending"
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "claimed"
        db_run.started_at = None

        self.service.mark_running(self.db, db_run, lease_seconds=3600)

        self.assertEqual(db_run.status, "running")
        self.assertEqual(db_run.lease_expires_at, self.now + timedelta(seconds=3600))

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_preserves_existing_lease_when_not_provided(
        self, mock_repo: MagicMock
    ) -> None:
        db_session = MagicMock()
        db_session.status = "running"
        mock_repo.get_by_id_for_update.return_value = db_session

        existing_lease = datetime(2026, 4, 29, 13, 0, tzinfo=timezone.utc)
        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.started_at = self.now
        db_run.lease_expires_at = existing_lease

        self.service.mark_running(self.db, db_run)

        # Lease preserved when not explicitly set
        self.assertEqual(db_run.lease_expires_at, existing_lease)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_updates_lease_when_provided(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        db_session.status = "running"
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.started_at = self.now
        db_run.lease_expires_at = datetime(2026, 4, 29, 13, 0, tzinfo=timezone.utc)

        self.service.mark_running(self.db, db_run, lease_seconds=7200)

        self.assertEqual(db_run.lease_expires_at, self.now + timedelta(seconds=7200))

    # --- Session status handling ---

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_session_not_set_to_running_when_canceled(
        self, mock_repo: MagicMock
    ) -> None:
        db_session = MagicMock()
        db_session.status = "canceled"
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.started_at = self.now

        self.service.mark_running(self.db, db_run)

        # Session status should NOT be changed from "canceled"
        self.assertEqual(db_session.status, "canceled")


class TestRunLifecycleServiceFinalizeTerminal(unittest.TestCase):
    """RunLifecycleService.finalize_terminal — all from-status × 3 to-status combinations."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        self.queue_service = MagicMock()
        self.service = RunLifecycleService(
            clock=FixedClock(self.now),
            session_queue_service=self.queue_service,
        )
        self.db = MagicMock()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_session_not_found(self, mock_repo: MagicMock) -> None:
        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        mock_repo.get_by_id_for_update.return_value = None

        for to_status in ["completed", "failed", "canceled"]:
            result = self.service.finalize_terminal(self.db, db_run, status=to_status)

            self.assertIsInstance(result, FinalizeTerminalResult)
            self.assertIsNone(result.session)
            self.assertIsNone(result.promoted_run)
            self.assertFalse(result.transition_applied)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_already_terminal_idempotent(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        # Test all 9 idempotent combinations: 3 terminal from × 3 terminal to
        for from_status in ["completed", "failed", "canceled"]:
            for to_status in ["completed", "failed", "canceled"]:
                db_run = MagicMock()
                db_run.session_id = uuid.uuid4()
                db_run.status = from_status
                db_run.last_error = None

                with self.subTest(from_status=from_status, to_status=to_status):
                    result = self.service.finalize_terminal(
                        self.db, db_run, status=to_status
                    )

                    self.assertEqual(result.session, db_session)
                    self.assertIsNone(result.promoted_run)
                    self.assertFalse(result.transition_applied)
                    # Status should remain unchanged
                    self.assertEqual(db_run.status, from_status)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_already_terminal_with_error_update(self, mock_repo: MagicMock) -> None:
        """Idempotent path should update last_error when missing."""
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "completed"
        db_run.last_error = None

        result = self.service.finalize_terminal(
            self.db, db_run, status="failed", error_message="New error"
        )

        self.assertFalse(result.transition_applied)
        self.assertEqual(db_run.last_error, "New error")

    # --- completed status ---

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_running_to_completed(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None
        db_run.last_error = None

        self.queue_service.promote_next_if_available.return_value = None

        result = self.service.finalize_terminal(self.db, db_run, status="completed")

        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "completed")
        self.assertEqual(db_run.progress, 100)
        self.assertEqual(db_run.finished_at, self.now)
        self.assertEqual(db_run.lease_expires_at, None)
        self.assertIsNone(db_run.last_error)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_claimed_to_completed(self, mock_repo: MagicMock) -> None:
        """claimed→completed is now BLOCKED by guard (only running can complete)."""
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "claimed"
        db_run.claimed_by = "worker-1"
        db_run.finished_at = None

        with self.assertRaises(AppException) as ctx:
            self.service.finalize_terminal(self.db, db_run, status="completed")
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_queued_to_completed(self, mock_repo: MagicMock) -> None:
        """queued→completed is now BLOCKED by guard (only running can complete)."""
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "queued"
        db_run.finished_at = None

        with self.assertRaises(AppException) as ctx:
            self.service.finalize_terminal(self.db, db_run, status="completed")
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_completed_with_promoted_run(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        promoted = MagicMock()
        self.queue_service.promote_next_if_available.return_value = promoted

        result = self.service.finalize_terminal(self.db, db_run, status="completed")

        self.assertTrue(result.transition_applied)
        self.assertEqual(result.promoted_run, promoted)

    # --- failed status ---

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_running_to_failed(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        result = self.service.finalize_terminal(
            self.db, db_run, status="failed", error_message="Something broke"
        )

        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "failed")
        self.assertEqual(db_run.last_error, "Something broke")
        self.assertEqual(db_run.finished_at, self.now)
        self.assertEqual(db_run.lease_expires_at, None)
        self.queue_service.pause_active_items.assert_called_once()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_claimed_to_failed(self, mock_repo: MagicMock) -> None:
        """claimed→failed is allowed (claimed is in the allowed set)."""
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "claimed"
        db_run.claimed_by = "worker-1"
        db_run.finished_at = None

        result = self.service.finalize_terminal(
            self.db, db_run, status="failed", error_message="claim failed"
        )

        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "failed")

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_queued_to_failed(self, mock_repo: MagicMock) -> None:
        """queued→failed is now BLOCKED by guard."""
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "queued"
        db_run.finished_at = None

        with self.assertRaises(AppException) as ctx:
            self.service.finalize_terminal(
                self.db, db_run, status="failed", error_message="error before claim"
            )
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    # --- canceled status ---

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_running_to_canceled(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        result = self.service.finalize_terminal(self.db, db_run, status="canceled")

        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "canceled")
        self.assertEqual(db_run.finished_at, self.now)
        self.assertEqual(db_run.lease_expires_at, None)
        self.queue_service.cancel_active_items.assert_called_once()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_queued_to_canceled(self, mock_repo: MagicMock) -> None:
        """queued→canceled is allowed (any non-terminal status can cancel)."""
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "queued"
        db_run.finished_at = None

        result = self.service.finalize_terminal(self.db, db_run, status="canceled")

        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "canceled")


if __name__ == "__main__":
    unittest.main()
