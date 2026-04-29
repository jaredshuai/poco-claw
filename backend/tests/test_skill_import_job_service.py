import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.skill_import import SkillImportCommitResponse
from app.services.skill_import_job_service import SkillImportJobService


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


class TestSkillImportJobServiceProcessCommitJob(unittest.TestCase):
    """Test SkillImportJobService.process_commit_job."""

    def setUp(self) -> None:
        self.now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        self.db = MagicMock()
        self.import_service = MagicMock()

    def _make_job(self) -> MagicMock:
        job = MagicMock()
        job.status = "queued"
        job.progress = 0
        job.archive_key = "imports/skills/archive.zip"
        job.selections = [{"relative_path": "skills/example/SKILL.md"}]
        job.user_id = "user-123"
        job.started_at = None
        job.finished_at = None
        job.error = None
        return job

    @patch("app.services.skill_import_job_service.SkillImportJobRepository")
    @patch("app.services.skill_import_job_service.SessionLocal")
    def test_process_commit_job_uses_clock_for_success_timestamps(
        self, mock_session_local: MagicMock, mock_job_repo: MagicMock
    ) -> None:
        mock_session_local.return_value = self.db
        job = self._make_job()
        mock_job_repo.get_by_id.return_value = job
        self.import_service.commit.return_value = SkillImportCommitResponse()
        service = SkillImportJobService(
            import_service=self.import_service,
            clock=FixedClock(self.now),
        )

        service.process_commit_job(uuid.uuid4())

        self.assertEqual(job.started_at, self.now)
        self.assertEqual(job.finished_at, self.now)
        self.assertEqual(job.status, "success")
        self.assertEqual(job.progress, 100)
        self.assertIsNone(job.error)

    @patch("app.services.skill_import_job_service.SkillImportJobRepository")
    @patch("app.services.skill_import_job_service.SessionLocal")
    def test_process_commit_job_uses_clock_for_failed_timestamp(
        self, mock_session_local: MagicMock, mock_job_repo: MagicMock
    ) -> None:
        mock_session_local.return_value = self.db
        job = self._make_job()
        mock_job_repo.get_by_id.return_value = job
        self.import_service.commit.side_effect = RuntimeError("boom")
        service = SkillImportJobService(
            import_service=self.import_service,
            clock=FixedClock(self.now),
        )

        service.process_commit_job(uuid.uuid4())

        self.assertEqual(job.started_at, self.now)
        self.assertEqual(job.finished_at, self.now)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, "boom")
        self.db.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
