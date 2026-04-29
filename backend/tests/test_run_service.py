import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.run import RunClaimRequest, RunFailRequest, RunStartRequest
from app.services.run_service import RunService


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
    mock_run.lease_expires_at = None
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


class TestRunServiceGetRun(unittest.TestCase):
    """Test get_run method."""

    def test_run_not_found(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = None
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.get_run(db, run_id)
            self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    def test_run_found(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        mock_run = create_mock_run(run_id=run_id, status="running")

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch("app.services.run_service.usage_service") as mock_usage:
                mock_usage.get_usage_summary_by_run.return_value = None
                service = RunService()
                result = service.get_run(db, run_id)
                self.assertIsNotNone(result)
                self.assertEqual(result.run_id, run_id)


class TestRunServiceListRuns(unittest.TestCase):
    """Test list_runs method."""

    def test_empty_list(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.list_by_session.return_value = []
            with patch("app.services.run_service.usage_service") as mock_usage:
                mock_usage.get_usage_summaries_by_run_ids.return_value = {}
                service = RunService()
                result = service.list_runs(db, session_id)
                self.assertEqual(result, [])

    def test_with_runs(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        run_id = uuid.uuid4()

        mock_run = create_mock_run(
            run_id=run_id, session_id=session_id, status="completed"
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.list_by_session.return_value = [mock_run]
            with patch("app.services.run_service.usage_service") as mock_usage:
                mock_usage.get_usage_summaries_by_run_ids.return_value = {}
                service = RunService()
                result = service.list_runs(db, session_id)
                self.assertEqual(len(result), 1)


class TestRunServiceClaimNextRun(unittest.TestCase):
    """Test claim_next_run method."""

    def test_empty_worker_id(self) -> None:
        db = MagicMock()
        request = RunClaimRequest(worker_id="   ")
        service = RunService()
        with self.assertRaises(AppException) as ctx:
            service.claim_next_run(db, request)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_no_run_available(self) -> None:
        db = MagicMock()
        request = RunClaimRequest(worker_id="worker-1")
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.claim_next.return_value = None
            service = RunService()
            result = service.claim_next_run(db, request)
            self.assertIsNone(result)
            db.commit.assert_called_once()

    def test_normalizes_non_positive_lease_seconds_before_claiming(self) -> None:
        db = MagicMock()
        request = RunClaimRequest(worker_id="worker-1", lease_seconds=0)
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.claim_next.return_value = None
            service = RunService()
            result = service.claim_next_run(db, request)
            self.assertIsNone(result)
            call_args = mock_repo.claim_next.call_args
            self.assertEqual(call_args.kwargs["lease_seconds"], 30)

    def test_passes_current_time_to_claim_repository(self) -> None:
        db = MagicMock()
        now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
        request = RunClaimRequest(worker_id="worker-1")
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.claim_next.return_value = None
            service = RunService(clock=FixedClock(now))
            result = service.claim_next_run(db, request)
            self.assertIsNone(result)
            call_args = mock_repo.claim_next.call_args
            self.assertEqual(call_args.kwargs["now"], now)

    def test_session_not_found(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        request = RunClaimRequest(worker_id="worker-1")

        mock_run = create_mock_run(run_id=run_id, session_id=session_id)

        with patch("app.services.run_service.RunRepository") as mock_run_repo:
            mock_run_repo.claim_next.return_value = mock_run
            with patch(
                "app.services.run_service.SessionRepository"
            ) as mock_session_repo:
                mock_session_repo.get_by_id.return_value = None
                service = RunService()
                with self.assertRaises(AppException) as ctx:
                    service.claim_next_run(db, request)
                self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    def test_message_not_found(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        request = RunClaimRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, session_id=session_id, user_message_id=123
        )

        mock_session = MagicMock()
        mock_session.id = session_id

        with patch("app.services.run_service.RunRepository") as mock_run_repo:
            mock_run_repo.claim_next.return_value = mock_run
            with patch(
                "app.services.run_service.SessionRepository"
            ) as mock_session_repo:
                mock_session_repo.get_by_id.return_value = mock_session
                with patch(
                    "app.services.run_service.MessageRepository"
                ) as mock_msg_repo:
                    mock_msg_repo.get_by_id.return_value = None
                    service = RunService()
                    with self.assertRaises(AppException) as ctx:
                        service.claim_next_run(db, request)
                    self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    def test_unable_to_extract_prompt(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        request = RunClaimRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, session_id=session_id, user_message_id=456
        )

        mock_session = MagicMock()
        mock_session.id = session_id

        mock_message = MagicMock()
        mock_message.content = "invalid"
        mock_message.text_preview = None

        with patch("app.services.run_service.RunRepository") as mock_run_repo:
            mock_run_repo.claim_next.return_value = mock_run
            with patch(
                "app.services.run_service.SessionRepository"
            ) as mock_session_repo:
                mock_session_repo.get_by_id.return_value = mock_session
                with patch(
                    "app.services.run_service.MessageRepository"
                ) as mock_msg_repo:
                    mock_msg_repo.get_by_id.return_value = mock_message
                    service = RunService()
                    with self.assertRaises(AppException) as ctx:
                        service.claim_next_run(db, request)
                    self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_successful_claim(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        request = RunClaimRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, session_id=session_id, status="claimed", user_message_id=789
        )

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = "user-123"
        mock_session.config_snapshot = {}
        mock_session.sdk_session_id = "sdk-123"

        mock_message = MagicMock()
        mock_message.content = {"content": [{"_type": "TextBlock", "text": "Hello"}]}
        mock_message.text_preview = "Hello"

        with patch("app.services.run_service.RunRepository") as mock_run_repo:
            mock_run_repo.claim_next.return_value = mock_run
            with patch(
                "app.services.run_service.SessionRepository"
            ) as mock_session_repo:
                mock_session_repo.get_by_id.return_value = mock_session
                with patch(
                    "app.services.run_service.MessageRepository"
                ) as mock_msg_repo:
                    mock_msg_repo.get_by_id.return_value = mock_message
                    service = RunService()
                    result = service.claim_next_run(db, request)
                    self.assertIsNotNone(result)
                    assert result is not None  # for type checker
                    self.assertEqual(result.user_id, "user-123")
                    self.assertEqual(result.prompt, "Hello")

    def test_with_schedule_modes(self) -> None:
        db = MagicMock()
        request = RunClaimRequest(
            worker_id="worker-1", schedule_modes=["immediate", "nightly"]
        )
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.claim_next.return_value = None
            service = RunService()
            result = service.claim_next_run(db, request)
            self.assertIsNone(result)
            # Verify schedule_modes was passed correctly
            call_args = mock_repo.claim_next.call_args
            self.assertEqual(
                call_args.kwargs["schedule_modes"], ["immediate", "nightly"]
            )

    def test_uses_text_preview_as_fallback(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        request = RunClaimRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, session_id=session_id, status="claimed", user_message_id=999
        )

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = "user-123"
        mock_session.config_snapshot = {}
        mock_session.sdk_session_id = "sdk-123"

        mock_message = MagicMock()
        mock_message.content = "invalid"  # Can't extract from this
        mock_message.text_preview = "Fallback text"

        with patch("app.services.run_service.RunRepository") as mock_run_repo:
            mock_run_repo.claim_next.return_value = mock_run
            with patch(
                "app.services.run_service.SessionRepository"
            ) as mock_session_repo:
                mock_session_repo.get_by_id.return_value = mock_session
                with patch(
                    "app.services.run_service.MessageRepository"
                ) as mock_msg_repo:
                    mock_msg_repo.get_by_id.return_value = mock_message
                    service = RunService()
                    result = service.claim_next_run(db, request)
                    self.assertIsNotNone(result)
                    assert result is not None
                    self.assertEqual(result.prompt, "Fallback text")


class TestRunServiceStartRun(unittest.TestCase):
    """Test start_run method."""

    def test_empty_worker_id(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="   ")
        service = RunService()
        with self.assertRaises(AppException) as ctx:
            service.start_run(db, run_id, request)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_run_not_found(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = None
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.start_run(db, run_id, request)
            self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    def test_run_already_completed(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(run_id=run_id, status="completed")

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            result = service.start_run(db, run_id, request)
            self.assertIsNotNone(result)

    def test_run_already_failed(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(run_id=run_id, status="failed")

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            result = service.start_run(db, run_id, request)
            self.assertIsNotNone(result)

    def test_run_already_canceled(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(run_id=run_id, status="canceled")

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            result = service.start_run(db, run_id, request)
            self.assertIsNotNone(result)

    def test_run_running_same_worker(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, status="running", claimed_by="worker-1"
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            result = service.start_run(db, run_id, request)
            self.assertIsNotNone(result)

    def test_run_running_different_worker(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, status="running", claimed_by="worker-2"
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.start_run(db, run_id, request)
            self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_run_invalid_status(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(run_id=run_id, status="unknown")

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.start_run(db, run_id, request)
            self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_run_claimed_by_different_worker(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, status="claimed", claimed_by="worker-2"
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.start_run(db, run_id, request)
            self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_run_start_from_claimed(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, status="claimed", claimed_by="worker-1"
        )
        mock_run.lease_expires_at = future_lease()
        mock_run.attempts = 0

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                result = service.start_run(db, run_id, request)
                self.assertIsNotNone(result)
                mock_lifecycle.mark_running.assert_called_once()
                db.commit.assert_called_once()

    def test_run_start_passes_current_time_to_transition_policy(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        request = RunStartRequest(worker_id="worker-1")
        mock_run = create_mock_run(
            run_id=run_id,
            status="running",
            claimed_by="worker-1",
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch("app.services.run_service.RunTransitionPolicy") as mock_policy:
                mock_policy.evaluate_start.return_value = "noop"
                service = RunService(clock=FixedClock(now))
                result = service.start_run(db, run_id, request)
                self.assertIsNotNone(result)
                call_args = mock_policy.evaluate_start.call_args
                self.assertEqual(call_args.kwargs["now"], now)

    def test_run_start_rejects_unclaimed_queued_run(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(run_id=run_id, status="queued", claimed_by=None)
        mock_run.attempts = 0

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                with self.assertRaises(AppException) as ctx:
                    service.start_run(db, run_id, request)
                self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)
                mock_lifecycle.mark_running.assert_not_called()

    def test_run_start_rejects_expired_claim(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunStartRequest(worker_id="worker-1")

        mock_run = create_mock_run(
            run_id=run_id, status="claimed", claimed_by="worker-1"
        )
        mock_run.lease_expires_at = expired_lease()

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                with self.assertRaises(AppException) as ctx:
                    service.start_run(db, run_id, request)
                self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)
                mock_lifecycle.mark_running.assert_not_called()


class TestRunServiceFailRun(unittest.TestCase):
    """Test fail_run method."""

    def test_empty_worker_id(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="   ", error_message="Error")
        service = RunService()
        with self.assertRaises(AppException) as ctx:
            service.fail_run(db, run_id, request)
        self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)

    def test_run_not_found(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")
        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = None
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.fail_run(db, run_id, request)
            self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    def test_run_already_terminal(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(run_id=run_id, status="completed")

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            result = service.fail_run(db, run_id, request)
            self.assertIsNotNone(result)

    def test_run_claimed_by_different_worker(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(
            run_id=run_id, status="running", claimed_by="worker-2"
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            service = RunService()
            with self.assertRaises(AppException) as ctx:
                service.fail_run(db, run_id, request)
            self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)

    def test_run_fail_success_with_started_at(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(
            run_id=run_id,
            status="running",
            claimed_by="worker-1",
            started_at=datetime.now(timezone.utc),
        )
        mock_run.lease_expires_at = expired_lease()

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                result = service.fail_run(db, run_id, request)
                self.assertIsNotNone(result)
                mock_lifecycle.finalize_terminal.assert_called_once()

    def test_run_fail_success_without_started_at(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(
            run_id=run_id,
            status="running",
            claimed_by="worker-1",
            started_at=None,
        )
        mock_run.lease_expires_at = expired_lease()

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                result = service.fail_run(db, run_id, request)
                self.assertIsNotNone(result)
                self.assertIsNotNone(mock_run.started_at)
                mock_lifecycle.finalize_terminal.assert_called_once()

    def test_run_fail_uses_current_time_for_transition_and_started_at(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        request = RunFailRequest(worker_id="worker-1", error_message="Error")
        mock_run = create_mock_run(
            run_id=run_id,
            status="running",
            claimed_by="worker-1",
            started_at=None,
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch("app.services.run_service.RunTransitionPolicy") as mock_policy:
                mock_policy.evaluate_fail.return_value = "apply"
                with patch(
                    "app.services.run_service.run_lifecycle_service"
                ) as mock_lifecycle:
                    service = RunService(clock=FixedClock(now))
                    result = service.fail_run(db, run_id, request)
                    self.assertIsNotNone(result)
                    call_args = mock_policy.evaluate_fail.call_args
                    self.assertEqual(call_args.kwargs["now"], now)
                    self.assertEqual(mock_run.started_at, now)
                    mock_lifecycle.finalize_terminal.assert_called_once()

    def test_run_fail_rejects_unclaimed_running_run(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(
            run_id=run_id,
            status="running",
            claimed_by=None,
            started_at=datetime.now(timezone.utc),
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                with self.assertRaises(AppException) as ctx:
                    service.fail_run(db, run_id, request)
                self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)
                mock_lifecycle.finalize_terminal.assert_not_called()

    def test_run_fail_rejects_unclaimed_queued_run(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(
            run_id=run_id,
            status="queued",
            claimed_by=None,
            started_at=None,
        )

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                with self.assertRaises(AppException) as ctx:
                    service.fail_run(db, run_id, request)
                self.assertEqual(ctx.exception.error_code, ErrorCode.BAD_REQUEST)
                mock_lifecycle.finalize_terminal.assert_not_called()

    def test_run_fail_rejects_expired_claim(self) -> None:
        db = MagicMock()
        run_id = uuid.uuid4()
        request = RunFailRequest(worker_id="worker-1", error_message="Error")

        mock_run = create_mock_run(
            run_id=run_id,
            status="claimed",
            claimed_by="worker-1",
            started_at=None,
        )
        mock_run.lease_expires_at = expired_lease()

        with patch("app.services.run_service.RunRepository") as mock_repo:
            mock_repo.get_by_id.return_value = mock_run
            with patch(
                "app.services.run_service.run_lifecycle_service"
            ) as mock_lifecycle:
                service = RunService()
                with self.assertRaises(AppException) as ctx:
                    service.fail_run(db, run_id, request)
                self.assertEqual(ctx.exception.error_code, ErrorCode.FORBIDDEN)
                mock_lifecycle.finalize_terminal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
