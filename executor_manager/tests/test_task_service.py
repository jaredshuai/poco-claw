import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.task import (
    SessionStatusResponse,
    TaskCreateResponse,
    TaskStatusResponse,
)
from app.services.task_service import TaskService


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


class TestTaskServiceInit(unittest.TestCase):
    """Test TaskService.__init__."""

    def test_init(self) -> None:
        """Test init creates settings."""
        mock_settings = MagicMock()

        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            service = TaskService()

            assert service.settings is mock_settings


class TestTaskServiceCreateTask(unittest.TestCase):
    """Test TaskService.create_task."""

    def _create_service(self) -> TaskService:
        """Create TaskService with mocked settings."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"

        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            return TaskService()

    def test_create_task_uses_injected_id_generator(self) -> None:
        """Test creating a task uses the injected task ID generator."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            service = TaskService(id_generator=FixedIdGenerator("task-fixed"))

        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(
            return_value={
                "session_id": "new-session-123",
                "sdk_session_id": "sdk-123",
            }
        )
        mock_scheduler = MagicMock()

        with (
            patch(
                "app.services.backend_client.BackendClient",
                return_value=mock_backend_client,
            ),
            patch("app.services.task_service.scheduler", mock_scheduler),
        ):
            import asyncio

            result = asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Test prompt",
                    config={"browser_enabled": False},
                    session_id=None,
                )
            )

        assert result.task_id == "task-fixed"
        assert mock_scheduler.add_job.call_args.kwargs["id"] == "task-fixed"
        assert mock_scheduler.add_job.call_args.kwargs["args"][0] == "task-fixed"

    def test_create_task_uses_injected_backend_client_factory(self) -> None:
        """Test creating a task can use an injected backend client boundary."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(
            return_value={
                "session_id": "new-session-123",
                "sdk_session_id": "sdk-123",
            }
        )
        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            service = TaskService(
                id_generator=FixedIdGenerator("task-fixed"),
                backend_client_factory=lambda: mock_backend_client,
            )

        mock_scheduler = MagicMock()

        with (
            patch(
                "app.services.backend_client.BackendClient",
                side_effect=AssertionError("backend client should be injected"),
            ),
            patch("app.services.task_service.scheduler", mock_scheduler),
        ):
            import asyncio

            result = asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Test prompt",
                    config={"browser_enabled": False},
                    session_id=None,
                )
            )

        assert result.task_id == "task-fixed"
        mock_backend_client.create_session.assert_called_once_with(
            user_id="user-123",
            config={"browser_enabled": False},
        )

    def test_create_task_new_session(self) -> None:
        """Test creating a task with a new session."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(
            return_value={
                "session_id": "new-session-123",
                "sdk_session_id": "sdk-123",
            }
        )

        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_scheduler.add_job = MagicMock(return_value=mock_job)

        mock_task_dispatcher = MagicMock()

        with (
            patch(
                "app.services.backend_client.BackendClient",
                return_value=mock_backend_client,
            ),
            patch("app.services.task_service.scheduler", mock_scheduler),
            patch("app.scheduler.task_dispatcher.TaskDispatcher", mock_task_dispatcher),
            patch(
                "app.core.observability.request_context.get_request_id",
                return_value="req-123",
            ),
            patch(
                "app.core.observability.request_context.get_trace_id",
                return_value="trace-123",
            ),
        ):
            import asyncio

            result = asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Test prompt",
                    config={"browser_enabled": False},
                    session_id=None,
                )
            )

            assert isinstance(result, TaskCreateResponse)
            assert result.session_id == "new-session-123"
            assert result.status == "scheduled"
            mock_backend_client.create_session.assert_called_once()
            mock_scheduler.add_job.assert_called_once()

    def test_create_task_continue_session(self) -> None:
        """Test creating a task with an existing session."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock()

        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_scheduler.add_job = MagicMock(return_value=mock_job)

        mock_task_dispatcher = MagicMock()

        # Mock get_session_status to return existing session
        mock_session_status = SessionStatusResponse(
            session_id="existing-session",
            user_id="user-123",
            sdk_session_id="sdk-existing",
            status="running",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with (
            patch(
                "app.services.backend_client.BackendClient",
                return_value=mock_backend_client,
            ),
            patch("app.services.task_service.scheduler", mock_scheduler),
            patch("app.scheduler.task_dispatcher.TaskDispatcher", mock_task_dispatcher),
            patch(
                "app.core.observability.request_context.get_request_id",
                return_value="req-123",
            ),
            patch(
                "app.core.observability.request_context.get_trace_id",
                return_value="trace-123",
            ),
            patch.object(
                service,
                "get_session_status",
                new_callable=AsyncMock,
                return_value=mock_session_status,
            ),
        ):
            import asyncio

            result = asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Continue prompt",
                    config={"browser_enabled": False},
                    session_id="existing-session",
                )
            )

            assert result.session_id == "existing-session"
            # Should NOT call create_session when continuing
            mock_backend_client.create_session.assert_not_called()

    def test_create_task_with_persistent_container(self) -> None:
        """Test creating a task with persistent container mode."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "sdk_session_id": "sdk-123",
            }
        )

        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_scheduler.add_job = MagicMock(return_value=mock_job)

        with (
            patch(
                "app.services.backend_client.BackendClient",
                return_value=mock_backend_client,
            ),
            patch("app.services.task_service.scheduler", mock_scheduler),
            patch(
                "app.scheduler.task_dispatcher.TaskDispatcher.resolve_executor_target",
                new_callable=AsyncMock,
                return_value=("container-123", "container-123"),
            ),
            patch(
                "app.core.observability.request_context.get_request_id",
                return_value="req-123",
            ),
            patch(
                "app.core.observability.request_context.get_trace_id",
                return_value="trace-123",
            ),
        ):
            import asyncio

            result = asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Test prompt",
                    config={"container_mode": "persistent", "browser_enabled": False},
                    session_id=None,
                )
            )

            assert result.container_id == "container-123"

    def test_create_task_with_container_id(self) -> None:
        """Test creating a task with a specific container ID."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "sdk_session_id": "sdk-123",
            }
        )

        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_scheduler.add_job = MagicMock(return_value=mock_job)

        with (
            patch(
                "app.services.backend_client.BackendClient",
                return_value=mock_backend_client,
            ),
            patch("app.services.task_service.scheduler", mock_scheduler),
            patch(
                "app.scheduler.task_dispatcher.TaskDispatcher.resolve_executor_target",
                new_callable=AsyncMock,
                return_value=("existing-container", "existing-container"),
            ),
            patch(
                "app.core.observability.request_context.get_request_id",
                return_value="req-123",
            ),
            patch(
                "app.core.observability.request_context.get_trace_id",
                return_value="trace-123",
            ),
        ):
            import asyncio

            asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Test prompt",
                    config={
                        "container_id": "existing-container",
                        "container_mode": "ephemeral",
                        "browser_enabled": False,
                    },
                    session_id=None,
                )
            )

    def test_create_task_http_error(self) -> None:
        """Test create_task handles HTTP errors."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Bad request"
        mock_backend_client.create_session = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=mock_response
            )
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            with self.assertRaises(AppException) as ctx:
                asyncio.run(
                    service.create_task(
                        user_id="user-123",
                        prompt="Test prompt",
                        config={"browser_enabled": False},
                        session_id=None,
                    )
                )

            assert ctx.exception.error_code == ErrorCode.SESSION_CREATE_FAILED

    def test_create_task_generic_error(self) -> None:
        """Test create_task handles generic errors."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            with self.assertRaises(AppException) as ctx:
                asyncio.run(
                    service.create_task(
                        user_id="user-123",
                        prompt="Test prompt",
                        config={"browser_enabled": False},
                        session_id=None,
                    )
                )

            assert ctx.exception.error_code == ErrorCode.TASK_SCHEDULING_FAILED


class TestTaskServiceGetTaskStatus(unittest.TestCase):
    """Test TaskService.get_task_status."""

    def _create_service(self) -> TaskService:
        """Create TaskService with mocked settings."""
        mock_settings = MagicMock()

        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            return TaskService()

    def test_get_task_status_found(self) -> None:
        """Test getting status of an existing task."""
        service = self._create_service()

        mock_job = MagicMock()
        mock_job.next_run_time = datetime.now()

        mock_scheduler = MagicMock()
        mock_scheduler.get_job = MagicMock(return_value=mock_job)

        with patch("app.services.task_service.scheduler", mock_scheduler):
            result = service.get_task_status("task-123")

            assert isinstance(result, TaskStatusResponse)
            assert result.task_id == "task-123"
            assert result.status == "scheduled"
            assert result.next_run_time is not None

    def test_get_task_status_not_found(self) -> None:
        """Test getting status of a non-existent task."""
        service = self._create_service()

        mock_scheduler = MagicMock()
        mock_scheduler.get_job = MagicMock(return_value=None)

        with patch("app.services.task_service.scheduler", mock_scheduler):
            with self.assertRaises(AppException) as ctx:
                service.get_task_status("nonexistent-task")

            assert ctx.exception.error_code == ErrorCode.TASK_NOT_FOUND
            assert "Task not found" in ctx.exception.message

    def test_get_task_status_no_next_run_time(self) -> None:
        """Test getting status when job has no next_run_time."""
        service = self._create_service()

        mock_job = MagicMock()
        mock_job.next_run_time = None

        mock_scheduler = MagicMock()
        mock_scheduler.get_job = MagicMock(return_value=mock_job)

        with patch("app.services.task_service.scheduler", mock_scheduler):
            result = service.get_task_status("task-123")

            assert result.next_run_time is None


class TestTaskServiceGetSessionStatus(unittest.TestCase):
    """Test TaskService.get_session_status."""

    def _create_service(self) -> TaskService:
        """Create TaskService with mocked settings."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"

        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            return TaskService()

    def test_get_session_status_uses_backend_client_boundary(self) -> None:
        """Test session status lookup delegates HTTP details to the backend client."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_backend_client = MagicMock()
        mock_backend_client.get_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "user_id": "user-123",
                "sdk_session_id": "sdk-123",
                "status": "running",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T01:00:00Z",
            }
        )
        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            service = TaskService(
                backend_client_factory=lambda: mock_backend_client,
            )

        with patch(
            "app.services.task_service.httpx.AsyncClient",
            side_effect=AssertionError("http client should stay inside adapter"),
        ):
            import asyncio

            result = asyncio.run(service.get_session_status("session-123"))

        assert result.session_id == "session-123"
        mock_backend_client.get_session.assert_awaited_once_with("session-123")

    def test_get_session_status_success(self) -> None:
        """Test getting session status successfully."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.get_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "user_id": "user-123",
                "sdk_session_id": "sdk-123",
                "status": "running",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T01:00:00Z",
            }
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            result = asyncio.run(service.get_session_status("session-123"))

            assert isinstance(result, SessionStatusResponse)
            assert result.session_id == "session-123"
            assert result.user_id == "user-123"
            mock_backend_client.get_session.assert_awaited_once_with("session-123")

    def test_get_session_status_not_found(self) -> None:
        """Test getting non-existent session status."""
        service = self._create_service()

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_backend_client = MagicMock()
        mock_backend_client.get_session = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            with self.assertRaises(AppException) as ctx:
                asyncio.run(service.get_session_status("nonexistent-session"))

            assert ctx.exception.error_code == ErrorCode.SESSION_NOT_FOUND

    def test_get_session_status_backend_unavailable(self) -> None:
        """Test handling backend unavailable error."""
        service = self._create_service()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        mock_backend_client = MagicMock()
        mock_backend_client.get_session = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            with self.assertRaises(AppException) as ctx:
                asyncio.run(service.get_session_status("session-123"))

            assert ctx.exception.error_code == ErrorCode.BACKEND_UNAVAILABLE

    def test_get_session_status_generic_error(self) -> None:
        """Test handling generic errors."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.get_session = AsyncMock(
            side_effect=Exception("Network error")
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            with self.assertRaises(AppException) as ctx:
                asyncio.run(service.get_session_status("session-123"))

            assert ctx.exception.error_code == ErrorCode.BACKEND_UNAVAILABLE

    def test_get_session_status_unwrapped_response(self) -> None:
        """Test handling already-unwrapped session data from the backend client."""
        service = self._create_service()

        mock_backend_client = MagicMock()
        mock_backend_client.get_session = AsyncMock(
            return_value={
                "session_id": "session-123",
                "user_id": "user-123",
                "status": "running",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T01:00:00Z",
            }
        )

        with patch(
            "app.services.backend_client.BackendClient",
            return_value=mock_backend_client,
        ):
            import asyncio

            result = asyncio.run(service.get_session_status("session-123"))

            assert result.session_id == "session-123"


if __name__ == "__main__":
    unittest.main()
