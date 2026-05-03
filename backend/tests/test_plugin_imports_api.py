"""Tests for Plugin Imports API Actor boundary.

These tests verify the HTTP adapter boundary correctly:
- Uses Actor.user_id when calling service methods
- Passes parameters unchanged to services
- Returns the expected success message with the exact data object
"""

import importlib.util
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

from app.core.identity import Actor
from app.schemas.plugin_import import (
    PluginImportCommitEnqueueResponse,
    PluginImportDiscoverResponse,
    PluginImportJobResponse,
)


def _load_plugin_imports_module_from_source():
    module_name = "_plugin_imports_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "plugin_imports.py"
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


def test_plugin_imports_module_import_does_not_initialize_storage_service() -> None:
    with patch(
        "app.services.storage_service.S3StorageService",
        side_effect=AssertionError("storage should be lazy"),
    ):
        module = _load_plugin_imports_module_from_source()

    assert module.discover_plugin_import is not None


@contextmanager
def _mock_import_service(
    result: Any = None,
) -> Generator[MagicMock, None, None]:
    """Context manager to mock get_import_service."""
    mock_service = MagicMock()
    mock_service.discover.return_value = result
    with patch(
        "app.api.v1.plugin_imports.get_import_service", return_value=mock_service
    ):
        yield mock_service


@contextmanager
def _mock_job_service(
    result: Any = None,
) -> Generator[MagicMock, None, None]:
    """Context manager to mock get_job_service."""
    mock_service = MagicMock()
    mock_service.enqueue_commit.return_value = result
    mock_service.get_job.return_value = result
    with patch("app.api.v1.plugin_imports.get_job_service", return_value=mock_service):
        yield mock_service


@contextmanager
def _mock_response_success() -> Generator[MagicMock, None, None]:
    """Context manager to mock Response.success."""
    with patch("app.api.v1.plugin_imports.Response.success") as mock_success:
        mock_success.return_value = MagicMock(status_code=200, body=b'{"data":{}}')
        yield mock_success


class TestDiscoverPluginImportActorBoundary:
    """Tests for discover_plugin_import endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to PluginImportService.discover."""
        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock()
        mock_result = PluginImportDiscoverResponse(
            archive_key="test-key", candidates=[]
        )

        with _mock_import_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import discover_plugin_import

            discover_plugin_import(
                file=None,
                github_url=None,
                actor=actor,
                db=mock_db,
            )

        call_kwargs = mock_service.discover.call_args[1]
        assert call_kwargs["user_id"] == "test-user-123"

    def test_passes_parameters_unchanged(self) -> None:
        """Verify file and github_url are passed unchanged."""
        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock()
        mock_file = MagicMock()
        mock_result = PluginImportDiscoverResponse(archive_key="key", candidates=[])

        with _mock_import_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import discover_plugin_import

            discover_plugin_import(
                file=mock_file,
                github_url="https://github.com/test/repo",
                actor=actor,
                db=mock_db,
            )

        call_kwargs = mock_service.discover.call_args[1]
        assert call_kwargs["file"] is mock_file
        assert call_kwargs["github_url"] == "https://github.com/test/repo"

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message and data object."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock()
        mock_result = PluginImportDiscoverResponse(
            archive_key="archive-key", candidates=[]
        )

        with _mock_import_service(mock_result):
            with _mock_response_success() as mock_success:
                from app.api.v1.plugin_imports import discover_plugin_import

                discover_plugin_import(
                    file=None,
                    github_url=None,
                    actor=actor,
                    db=mock_db,
                )

        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "Plugin import discovered"
        assert call_kwargs["data"] is mock_result


class TestCommitPluginImportActorBoundary:
    """Tests for commit_plugin_import endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to PluginImportJobService.enqueue_commit."""
        actor = Actor(user_id="test-user-789", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_bg = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportCommitEnqueueResponse(
            job_id=test_job_id, status="queued"
        )

        with _mock_job_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import commit_plugin_import

            commit_plugin_import(
                request=mock_request,
                background_tasks=mock_bg,
                actor=actor,
                db=mock_db,
            )

        call_kwargs = mock_service.enqueue_commit.call_args[1]
        assert call_kwargs["user_id"] == "test-user-789"

    def test_passes_request_unchanged(self) -> None:
        """Verify request is passed unchanged to enqueue_commit."""
        actor = Actor(user_id="test-user-req", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_bg = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportCommitEnqueueResponse(
            job_id=test_job_id, status="queued"
        )

        with _mock_job_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import commit_plugin_import

            commit_plugin_import(
                request=mock_request,
                background_tasks=mock_bg,
                actor=actor,
                db=mock_db,
            )

        call_kwargs = mock_service.enqueue_commit.call_args[1]
        assert call_kwargs["request"] is mock_request

    def test_schedules_background_task(self) -> None:
        """Verify background_tasks.add_task is called with service.process_commit_job."""
        actor = Actor(user_id="test-user-bg", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_bg = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportCommitEnqueueResponse(
            job_id=test_job_id, status="queued"
        )

        with _mock_job_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import commit_plugin_import

            commit_plugin_import(
                request=mock_request,
                background_tasks=mock_bg,
                actor=actor,
                db=mock_db,
            )

        mock_bg.add_task.assert_called_once_with(
            mock_service.process_commit_job,
            test_job_id,
        )

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message and data object."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_bg = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportCommitEnqueueResponse(
            job_id=test_job_id, status="queued"
        )

        with _mock_job_service(mock_result):
            with _mock_response_success() as mock_success:
                from app.api.v1.plugin_imports import commit_plugin_import

                commit_plugin_import(
                    request=mock_request,
                    background_tasks=mock_bg,
                    actor=actor,
                    db=mock_db,
                )

        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "Plugin import queued"
        assert call_kwargs["data"] is mock_result


class TestGetPluginImportJobActorBoundary:
    """Tests for get_plugin_import_job endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to PluginImportJobService.get_job."""
        actor = Actor(user_id="test-user-job", auth_source="test")
        mock_db = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportJobResponse(job_id=test_job_id, status="completed")

        with _mock_job_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import get_plugin_import_job

            get_plugin_import_job(
                job_id=test_job_id,
                actor=actor,
                db=mock_db,
            )

        call_kwargs = mock_service.get_job.call_args[1]
        assert call_kwargs["user_id"] == "test-user-job"

    def test_passes_job_id_unchanged(self) -> None:
        """Verify job_id is passed unchanged to get_job."""
        actor = Actor(user_id="test-user-jid", auth_source="test")
        mock_db = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportJobResponse(job_id=test_job_id, status="completed")

        with _mock_job_service(mock_result) as mock_service:
            from app.api.v1.plugin_imports import get_plugin_import_job

            get_plugin_import_job(
                job_id=test_job_id,
                actor=actor,
                db=mock_db,
            )

        call_kwargs = mock_service.get_job.call_args[1]
        assert call_kwargs["job_id"] == test_job_id

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message and data object."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock()
        test_job_id = uuid.uuid4()
        mock_result = PluginImportJobResponse(job_id=test_job_id, status="completed")

        with _mock_job_service(mock_result):
            with _mock_response_success() as mock_success:
                from app.api.v1.plugin_imports import get_plugin_import_job

                get_plugin_import_job(
                    job_id=test_job_id,
                    actor=actor,
                    db=mock_db,
                )

        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "Plugin import job retrieved"
        assert call_kwargs["data"] is mock_result
