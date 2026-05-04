import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.services.run_lifecycle_service import (
    FinalizeTerminalResult,
    RunLifecycleService,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


class TestRunLifecycleServiceSyncScheduledTask(unittest.TestCase):
    """Test RunLifecycleService._sync_scheduled_task_last_status."""

    def setUp(self) -> None:
        self.service = RunLifecycleService()
        self.db = MagicMock()

    def test_no_scheduled_task_id(self) -> None:
        db_run = MagicMock()
        db_run.scheduled_task_id = None

        self.service._sync_scheduled_task_last_status(self.db, db_run)

    @patch("app.services.run_lifecycle_service.ScheduledTaskRepository")
    def test_task_not_found(self, mock_repo: MagicMock) -> None:
        db_run = MagicMock()
        db_run.scheduled_task_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = None

        self.service._sync_scheduled_task_last_status(self.db, db_run)

        mock_repo.get_by_id.assert_called_once()

    @patch("app.services.run_lifecycle_service.ScheduledTaskRepository")
    def test_different_last_run_id(self, mock_repo: MagicMock) -> None:
        db_run = MagicMock()
        db_run.scheduled_task_id = uuid.uuid4()
        db_run.id = 123
        db_run.status = "completed"

        db_task = MagicMock()
        db_task.last_run_id = 456
        mock_repo.get_by_id.return_value = db_task

        self.service._sync_scheduled_task_last_status(self.db, db_run)

        self.assertEqual(db_task.last_run_id, 456)

    @patch("app.services.run_lifecycle_service.ScheduledTaskRepository")
    def test_updates_on_matching_last_run_id(self, mock_repo: MagicMock) -> None:
        run_id = 123
        db_run = MagicMock()
        db_run.scheduled_task_id = uuid.uuid4()
        db_run.id = run_id
        db_run.status = "completed"

        db_task = MagicMock()
        db_task.last_run_id = run_id
        mock_repo.get_by_id.return_value = db_task

        self.service._sync_scheduled_task_last_status(self.db, db_run)

        self.assertEqual(db_task.last_run_status, "completed")


class TestRunLifecycleServiceMarkRunning(unittest.TestCase):
    """Test RunLifecycleService.mark_running."""

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
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "completed"

        result = self.service.mark_running(self.db, db_run)

        self.assertEqual(result, db_session)

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
        self.queue_service.clear_execution_state.assert_called_once()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_mark_running_sets_lease_when_provided(self, mock_repo: MagicMock) -> None:
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
    def test_mark_running_preserves_existing_lease_when_not_provided(
        self, mock_repo: MagicMock
    ) -> None:
        db_session = MagicMock()
        db_session.status = "pending"
        mock_repo.get_by_id_for_update.return_value = db_session

        existing_lease = datetime(2026, 4, 29, 13, 0, tzinfo=timezone.utc)
        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.started_at = self.now
        db_run.lease_expires_at = existing_lease

        self.service.mark_running(self.db, db_run)

        # Lease should be preserved when not explicitly set
        self.assertEqual(db_run.lease_expires_at, existing_lease)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_mark_running_updates_lease_when_provided(
        self, mock_repo: MagicMock
    ) -> None:
        db_session = MagicMock()
        db_session.status = "pending"
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.started_at = self.now
        db_run.lease_expires_at = datetime(2026, 4, 29, 13, 0, tzinfo=timezone.utc)

        self.service.mark_running(self.db, db_run, lease_seconds=7200)

        # Lease should be updated to new value
        self.assertEqual(db_run.lease_expires_at, self.now + timedelta(seconds=7200))


class TestRunLifecycleServiceFinalizeTerminal(unittest.TestCase):
    """Test RunLifecycleService.finalize_terminal."""

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

        result = self.service.finalize_terminal(self.db, db_run, status="completed")

        self.assertIsInstance(result, FinalizeTerminalResult)
        self.assertIsNone(result.session)
        self.assertIsNone(result.promoted_run)
        self.assertFalse(result.transition_applied)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_already_terminal_returns_transition_not_applied(
        self, mock_repo: MagicMock
    ) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "completed"  # Already terminal
        db_run.last_error = None

        result = self.service.finalize_terminal(self.db, db_run, status="completed")

        self.assertIsInstance(result, FinalizeTerminalResult)
        self.assertEqual(result.session, db_session)
        self.assertIsNone(result.promoted_run)
        self.assertFalse(result.transition_applied)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_completed_status(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        self.queue_service.promote_next_if_available.return_value = None

        result = self.service.finalize_terminal(self.db, db_run, status="completed")

        self.assertIsInstance(result, FinalizeTerminalResult)
        self.assertEqual(result.session, db_session)
        self.assertIsNone(result.promoted_run)
        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "completed")
        self.assertEqual(db_run.progress, 100)
        self.assertEqual(db_run.finished_at, self.now)

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_failed_status(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        result = self.service.finalize_terminal(
            self.db, db_run, status="failed", error_message="Error message"
        )

        self.assertIsInstance(result, FinalizeTerminalResult)
        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "failed")
        self.assertEqual(db_run.last_error, "Error message")
        self.assertEqual(db_run.finished_at, self.now)
        self.queue_service.pause_active_items.assert_called_once()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_canceled_status(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        result = self.service.finalize_terminal(self.db, db_run, status="canceled")

        self.assertIsInstance(result, FinalizeTerminalResult)
        self.assertTrue(result.transition_applied)
        self.assertEqual(db_run.status, "canceled")
        self.assertEqual(db_run.finished_at, self.now)
        self.queue_service.cancel_active_items.assert_called_once()

    @patch("app.services.run_lifecycle_service.SessionRepository")
    def test_returns_promoted_run(self, mock_repo: MagicMock) -> None:
        db_session = MagicMock()
        mock_repo.get_by_id_for_update.return_value = db_session

        db_run = MagicMock()
        db_run.session_id = uuid.uuid4()
        db_run.status = "running"
        db_run.finished_at = None

        promoted_run = MagicMock()
        self.queue_service.promote_next_if_available.return_value = promoted_run

        result = self.service.finalize_terminal(self.db, db_run, status="completed")

        self.assertIsInstance(result, FinalizeTerminalResult)
        self.assertTrue(result.transition_applied)
        self.assertEqual(result.promoted_run, promoted_run)


if __name__ == "__main__":
    unittest.main()
