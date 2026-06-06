import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import get_args, get_origin
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.scheduler.task_dispatcher import TaskDispatchExecutorTarget
from app.schemas.task import (
    SessionStatusResponse,
    TaskConfig,
    TaskCreateResponse,
    TaskStatusResponse,
)
from app.services.task_service import (
    BackendTaskClient,
    TaskBackendClient,
    TaskDispatcherTargetResolver,
    TaskScheduler,
    TaskSchedulerJob,
    TaskService,
    TaskSessionCreation,
    TaskTargetResolver,
)


def _session_creation(
    session_id: str = "new-session-123",
    sdk_session_id: str | None = "sdk-123",
) -> TaskSessionCreation:
    return TaskSessionCreation(session_id=session_id, sdk_session_id=sdk_session_id)


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

    def test_init_accepts_injected_settings(self) -> None:
        """Test init can receive settings without reading global settings."""
        settings = SimpleNamespace()

        with patch(
            "app.services.task_service.get_settings",
            side_effect=AssertionError("settings should be injected"),
        ):
            service = TaskService(settings=settings)

        assert service.settings is settings

    def test_init_defers_default_target_resolver_construction(self) -> None:
        """Test init does not eagerly bind the task dispatcher adapter."""
        settings = SimpleNamespace()

        with patch(
            "app.services.task_service.TaskDispatcherTargetResolver",
            side_effect=AssertionError("target resolver should be lazy"),
        ):
            service = TaskService(settings=settings)

        assert service.settings is settings


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
        mock_backend_client.create_session = AsyncMock(return_value=_session_creation())
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

    def test_create_task_uses_injected_scheduler_and_target_resolver(self) -> None:
        """Test task scheduling and runtime target resolution use injected ports."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_backend_client = MagicMock()
        mock_backend_client.create_session = AsyncMock(return_value=_session_creation())
        mock_scheduler = MagicMock()
        mock_target_resolver = MagicMock()
        mock_target_resolver.resolve_executor_target = AsyncMock(
            return_value=TaskDispatchExecutorTarget(
                executor_url="http://executor.local",
                container_id="container-from-port",
            )
        )

        with patch(
            "app.services.task_service.get_settings", return_value=mock_settings
        ):
            service = TaskService(
                id_generator=FixedIdGenerator("task-fixed"),
                backend_client_factory=lambda: mock_backend_client,
                task_scheduler_factory=lambda: mock_scheduler,
                target_resolver=mock_target_resolver,
            )

        global_scheduler = MagicMock()
        global_scheduler.add_job.side_effect = AssertionError(
            "scheduler should be injected"
        )
        with (
            patch("app.services.task_service.scheduler", global_scheduler),
            patch(
                "app.scheduler.task_dispatcher.TaskDispatcher.resolve_executor_target",
                new_callable=AsyncMock,
                side_effect=AssertionError("target resolver should be injected"),
            ),
        ):
            import asyncio

            result = asyncio.run(
                service.create_task(
                    user_id="user-123",
                    prompt="Test prompt",
                    config={"container_mode": "persistent", "browser_enabled": True},
                    session_id=None,
                )
            )

        assert result.task_id == "task-fixed"
        assert result.container_id == "container-from-port"
        mock_scheduler.add_job.assert_called_once()
        mock_target_resolver.resolve_executor_target.assert_awaited_once_with(
            session_id="new-session-123",
            user_id="user-123",
            browser_enabled=True,
            container_mode="persistent",
            container_id=None,
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
                return_value=TaskDispatchExecutorTarget(
                    executor_url="http://executor.local",
                    container_id="container-123",
                ),
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
                return_value=TaskDispatchExecutorTarget(
                    executor_url="http://executor.local",
                    container_id="existing-container",
                ),
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


class TestTaskServiceBoundaryAnnotations(unittest.TestCase):
    """Regression tests for TaskService backend boundary annotations."""

    def test_task_config_payload_fields_are_dict_str_object(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskConfig)

        for field_name in ("mcp_config", "skill_files", "plugin_files"):
            field_type = hints.get(field_name)

            assert field_type is not None
            assert field_type is not dict
            assert "Any" not in str(field_type)
            assert get_origin(field_type) is dict
            assert get_args(field_type) == (str, object)

    def test_session_status_config_snapshot_is_optional_dict_str_object(self) -> None:
        import typing

        hints = typing.get_type_hints(SessionStatusResponse)
        field_type = hints.get("config_snapshot")

        assert field_type is not None
        assert field_type is not dict
        assert "Any" not in str(field_type)
        args = get_args(field_type)
        assert type(None) in args
        dict_type = next((arg for arg in args if get_origin(arg) is dict), None)
        assert dict_type is not None
        assert get_args(dict_type) == (str, object)

    def test_backend_client_create_session_config_is_dict_str_object(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskBackendClient.create_session)
        config_type = hints.get("config")

        assert get_origin(config_type) is dict
        assert get_args(config_type) == (str, object)

    def test_backend_client_create_session_return_is_named_session_creation(
        self,
    ) -> None:
        import typing

        hints = typing.get_type_hints(TaskBackendClient.create_session)
        return_type = hints.get("return")

        assert return_type is TaskSessionCreation

    def test_backend_task_client_normalizes_raw_create_session_payload(self) -> None:
        raw_backend_client = MagicMock()
        raw_backend_client.create_session = AsyncMock(
            return_value={
                "session_id": "session-from-backend",
                "sdk_session_id": "sdk-from-backend",
            }
        )

        client = BackendTaskClient(raw_backend_client)

        import asyncio

        result = asyncio.run(
            client.create_session(
                user_id="user-123",
                config={"browser_enabled": False},
            )
        )

        assert result == TaskSessionCreation(
            session_id="session-from-backend",
            sdk_session_id="sdk-from-backend",
        )

    def test_backend_client_get_session_return_is_dict_str_object(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskBackendClient.get_session)
        return_type = hints.get("return")

        assert get_origin(return_type) is dict
        assert get_args(return_type) == (str, object)

    def test_create_task_config_is_dict_str_object(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskService.create_task)
        config_type = hints.get("config")

        assert get_origin(config_type) is dict
        assert get_args(config_type) == (str, object)

    def test_target_resolver_returns_named_executor_target(self) -> None:
        import typing

        protocol_hints = typing.get_type_hints(
            TaskTargetResolver.resolve_executor_target
        )
        adapter_hints = typing.get_type_hints(
            TaskDispatcherTargetResolver.resolve_executor_target
        )

        assert protocol_hints.get("return") is TaskDispatchExecutorTarget
        assert adapter_hints.get("return") is TaskDispatchExecutorTarget

    def test_scheduler_add_job_return_is_object(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskScheduler.add_job)

        assert hints.get("return") is object

    def test_scheduler_add_job_kwargs_are_object(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskScheduler.add_job)

        assert hints.get("kwargs") is object

    def test_scheduler_get_job_returns_scheduler_job_or_none(self) -> None:
        import typing

        hints = typing.get_type_hints(TaskScheduler.get_job)
        return_type = hints.get("return")

        assert set(get_args(return_type)) == {TaskSchedulerJob, type(None)}


if __name__ == "__main__":
    unittest.main()
