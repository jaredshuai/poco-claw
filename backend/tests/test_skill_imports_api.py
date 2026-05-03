"""Route-level tests for the skill imports API module."""

import importlib.util
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import uuid

from app.core.identity import Actor


def _load_skill_imports_module_from_source():
    module_name = "_skill_imports_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "skill_imports.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def test_skill_imports_module_import_does_not_initialize_storage_service() -> None:
    with patch(
        "app.services.storage_service.S3StorageService",
        side_effect=AssertionError("storage should be lazy"),
    ):
        module = _load_skill_imports_module_from_source()

    assert module.discover_skill_import is not None


class TestDiscoverSkillImportActorBoundary:
    """Tests for discover_skill_import using actor.user_id."""

    def test_uses_actor_user_id_for_service_call(self) -> None:
        """discover_skill_import passes actor.user_id to SkillImportService.discover."""
        from app.api.v1.skill_imports import discover_skill_import

        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.archive_key = "test-key"

        with patch("app.api.v1.skill_imports.get_import_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.discover.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success") as mock_response:
                mock_response.return_value = MagicMock()

                discover_skill_import(
                    file=None,
                    github_url=None,
                    actor=actor,
                    db=mock_db,
                )

                mock_service.discover.assert_called_once()
                call_kwargs = mock_service.discover.call_args[1]
                assert call_kwargs["user_id"] == "test-user-123"

    def test_response_success_receives_correct_message(self) -> None:
        """Response.success is called with correct data and message."""
        from app.api.v1.skill_imports import discover_skill_import

        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.archive_key = "archive-key-789"

        with patch("app.api.v1.skill_imports.get_import_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.discover.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success") as mock_response:
                mock_response.return_value = MagicMock()

                discover_skill_import(
                    file=None,
                    github_url="https://github.com/test/repo",
                    actor=actor,
                    db=mock_db,
                )

                mock_response.assert_called_once_with(
                    data=mock_result, message="Skill import discovered"
                )


class TestCommitSkillImportActorBoundary:
    """Tests for commit_skill_import using actor.user_id."""

    def test_uses_actor_user_id_for_service_call(self) -> None:
        """commit_skill_import passes actor.user_id to SkillImportJobService.enqueue_commit."""
        from app.api.v1.skill_imports import commit_skill_import

        actor = Actor(user_id="commit-user-123", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.archive_key = "test-archive"
        mock_request.selections = []
        mock_result = MagicMock()
        mock_result.job_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

        with patch("app.api.v1.skill_imports.get_job_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.enqueue_commit.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success"):
                commit_skill_import(
                    request=mock_request,
                    background_tasks=MagicMock(),
                    actor=actor,
                    db=mock_db,
                )

                mock_service.enqueue_commit.assert_called_once()
                call_kwargs = mock_service.enqueue_commit.call_args[1]
                assert call_kwargs["user_id"] == "commit-user-123"

    def test_schedules_process_commit_job_with_job_id(self) -> None:
        """commit_skill_import schedules process_commit_job with the returned job_id."""
        from app.api.v1.skill_imports import commit_skill_import

        actor = Actor(user_id="commit-user-456", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.archive_key = "test-archive"
        mock_request.selections = []
        expected_job_id = uuid.UUID("abcdef01-2345-6789-abcd-ef0123456789")
        mock_result = MagicMock()
        mock_result.job_id = expected_job_id

        mock_background_tasks = MagicMock()

        with patch("app.api.v1.skill_imports.get_job_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.enqueue_commit.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success"):
                commit_skill_import(
                    request=mock_request,
                    background_tasks=mock_background_tasks,
                    actor=actor,
                    db=mock_db,
                )

                mock_background_tasks.add_task.assert_called_once_with(
                    mock_service.process_commit_job, expected_job_id
                )

    def test_response_success_receives_correct_message(self) -> None:
        """Response.success is called with correct data and message."""
        from app.api.v1.skill_imports import commit_skill_import

        actor = Actor(user_id="commit-user-789", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.archive_key = "test-archive"
        mock_request.selections = []
        mock_result = MagicMock()
        mock_result.job_id = uuid.UUID("11111111-2222-3333-4444-555555555555")

        with patch("app.api.v1.skill_imports.get_job_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.enqueue_commit.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success") as mock_response:
                mock_response.return_value = MagicMock()

                commit_skill_import(
                    request=mock_request,
                    background_tasks=MagicMock(),
                    actor=actor,
                    db=mock_db,
                )

                mock_response.assert_called_once_with(
                    data=mock_result, message="Skill import queued"
                )


class TestGetSkillImportJobActorBoundary:
    """Tests for get_skill_import_job using actor.user_id."""

    def test_uses_actor_user_id_for_service_call(self) -> None:
        """get_skill_import_job passes actor.user_id to SkillImportJobService.get_job."""
        from app.api.v1.skill_imports import get_skill_import_job

        actor = Actor(user_id="job-user-123", auth_source="test")
        mock_db = MagicMock()
        job_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        mock_result = MagicMock()
        mock_result.job_id = job_id

        with patch("app.api.v1.skill_imports.get_job_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_job.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success"):
                get_skill_import_job(
                    job_id=job_id,
                    actor=actor,
                    db=mock_db,
                )

                mock_service.get_job.assert_called_once()
                call_kwargs = mock_service.get_job.call_args[1]
                assert call_kwargs["user_id"] == "job-user-123"

    def test_response_success_receives_correct_message(self) -> None:
        """Response.success is called with correct data and message."""
        from app.api.v1.skill_imports import get_skill_import_job

        actor = Actor(user_id="job-user-456", auth_source="test")
        mock_db = MagicMock()
        job_id = uuid.UUID("ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb")
        mock_result = MagicMock()
        mock_result.job_id = job_id

        with patch("app.api.v1.skill_imports.get_job_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_job.return_value = mock_result
            mock_get_service.return_value = mock_service

            with patch("app.api.v1.skill_imports.Response.success") as mock_response:
                mock_response.return_value = MagicMock()

                get_skill_import_job(
                    job_id=job_id,
                    actor=actor,
                    db=mock_db,
                )

                mock_response.assert_called_once_with(
                    data=mock_result, message="Skill import job retrieved"
                )
