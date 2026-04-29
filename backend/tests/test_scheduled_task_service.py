import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.scheduled_task import (
    ScheduledTaskCreateRequest,
    ScheduledTaskUpdateRequest,
)
from app.services.scheduled_task_service import ScheduledTaskService


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


class TestScheduledTaskServiceClock(unittest.TestCase):
    """Test ScheduledTaskService clock boundaries."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        self.next_run_at = datetime(2026, 4, 29, 13, 0, tzinfo=timezone.utc)
        self.db = MagicMock()
        self.user_id = "user-123"

    def _make_task(self) -> MagicMock:
        task = MagicMock()
        task.id = uuid.uuid4()
        task.user_id = self.user_id
        task.name = "Daily task"
        task.cron = "0 * * * *"
        task.timezone = "UTC"
        task.prompt = "Run diagnostics"
        task.enabled = True
        task.reuse_session = False
        task.session_id = None
        task.config_snapshot = {}
        task.input_files = None
        task.next_run_at = self.next_run_at
        task.last_run_id = None
        task.last_run_status = None
        task.last_error = None
        task.created_at = self.now
        task.updated_at = self.now
        return task

    @patch("app.services.scheduled_task_service.ScheduledTaskResponse")
    @patch("app.services.scheduled_task_service.ScheduledTaskRepository")
    def test_create_task_computes_next_run_from_clock(
        self,
        mock_task_repo: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        task_service = MagicMock()
        task_service._build_config_snapshot.return_value = {}
        mock_task_repo.create.return_value = self._make_task()
        service = ScheduledTaskService(
            clock=FixedClock(self.now),
            task_service=task_service,
        )
        service._validate_timezone = MagicMock(return_value="UTC")
        service._compute_next_run_at = MagicMock(return_value=self.next_run_at)

        service.create_task(
            self.db,
            self.user_id,
            ScheduledTaskCreateRequest(
                name="Daily task",
                cron="0 * * * *",
                timezone="UTC",
                prompt="Run diagnostics",
                enabled=True,
                reuse_session=False,
            ),
        )

        service._compute_next_run_at.assert_called_once_with(
            cron_expr="0 * * * *",
            timezone_name="UTC",
            now_utc=self.now,
        )
        create_kwargs = mock_task_repo.create.call_args.kwargs
        self.assertEqual(create_kwargs["next_run_at"], self.next_run_at)
        task_service._build_config_snapshot.assert_called_once()
        mock_response.model_validate.assert_called_once()

    @patch("app.services.scheduled_task_service.ScheduledTaskResponse")
    @patch("app.services.scheduled_task_service.ScheduledTaskRepository")
    def test_update_task_recomputes_next_run_from_clock(
        self, mock_task_repo: MagicMock, mock_response: MagicMock
    ) -> None:
        task = self._make_task()
        mock_task_repo.get_by_id.return_value = task
        service = ScheduledTaskService(clock=FixedClock(self.now))
        service._compute_next_run_at = MagicMock(return_value=self.next_run_at)

        service.update_task(
            self.db,
            self.user_id,
            task.id,
            ScheduledTaskUpdateRequest(cron="30 * * * *"),
        )

        service._compute_next_run_at.assert_called_once_with(
            cron_expr="30 * * * *",
            timezone_name="UTC",
            now_utc=self.now,
        )
        mock_response.model_validate.assert_called_once()

    @patch("app.services.scheduled_task_service.ScheduledTaskRepository")
    def test_trigger_task_uses_clock_for_forced_run_scheduled_at(
        self, mock_task_repo: MagicMock
    ) -> None:
        task = self._make_task()
        run = MagicMock()
        run.id = uuid.uuid4()
        run.session_id = uuid.uuid4()
        run.status = "queued"
        mock_task_repo.get_by_id.return_value = task
        service = ScheduledTaskService(clock=FixedClock(self.now))
        service._enqueue_run_for_task = MagicMock(return_value=run)

        service.trigger_task(self.db, self.user_id, task.id)

        service._enqueue_run_for_task.assert_called_once_with(
            self.db,
            task=task,
            scheduled_at=self.now,
            force=True,
        )

    @patch("app.services.scheduled_task_service.ScheduledTaskRepository")
    def test_dispatch_due_claims_due_tasks_with_clock(
        self, mock_task_repo: MagicMock
    ) -> None:
        mock_task_repo.claim_due_for_update.return_value = []
        service = ScheduledTaskService(clock=FixedClock(self.now))

        service.dispatch_due(self.db, limit=25)

        mock_task_repo.claim_due_for_update.assert_called_once_with(
            self.db,
            limit=25,
            now_utc=self.now,
        )


if __name__ == "__main__":
    unittest.main()
