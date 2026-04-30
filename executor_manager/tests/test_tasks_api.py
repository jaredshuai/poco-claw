"""Tests for app/api/v1/tasks.py."""

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _load_tasks_module_from_source():
    module_name = "_tasks_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "tasks.py"
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


@contextmanager
def _service_override(app, mock_service):
    from app.api.v1 import tasks

    app.dependency_overrides[tasks.get_task_service] = lambda: mock_service
    try:
        yield
    finally:
        app.dependency_overrides.pop(tasks.get_task_service, None)


def test_tasks_module_import_does_not_initialize_service() -> None:
    with patch(
        "app.services.task_service.TaskService",
        side_effect=AssertionError("task service should be lazy"),
    ):
        module = _load_tasks_module_from_source()

    assert module.create_task is not None


def test_tasks_routes_use_service_dependency_override() -> None:
    from app.main import app

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "task_id": "task-123",
        "status": "running",
        "progress": 50,
    }
    mock_service = MagicMock()
    mock_service.get_task_status.return_value = mock_result

    with _service_override(app, mock_service):
        with patch(
            "app.api.v1.tasks.TaskService",
            side_effect=AssertionError("route should use service override"),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/tasks/task-123")

    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == "task-123"
    mock_service.get_task_status.assert_called_once_with("task-123")


def test_tasks_service_provider_has_no_mutable_global() -> None:
    from app.api.v1 import tasks

    assert not hasattr(tasks, "task_service")


class TestTasksEndpoints(unittest.TestCase):
    """Test /api/v1/tasks endpoints."""

    def test_create_task_success(self) -> None:
        """Test successful task creation."""
        from app.main import app

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "task_id": "task-123",
            "session_id": "session-123",
            "status": "pending",
        }

        mock_service = MagicMock()
        mock_service.create_task = AsyncMock(return_value=mock_result)

        with _service_override(app, mock_service):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tasks",
                json={
                    "user_id": "user-123",
                    "prompt": "Test prompt",
                    "config": {
                        "model": "claude-3",
                    },
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["task_id"] == "task-123"
            mock_service.create_task.assert_called_once()

    def test_create_task_with_session_id(self) -> None:
        """Test task creation with existing session_id."""
        from app.main import app

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "task_id": "task-456",
            "session_id": "existing-session",
            "status": "pending",
        }

        mock_service = MagicMock()
        mock_service.create_task = AsyncMock(return_value=mock_result)

        with _service_override(app, mock_service):
            client = TestClient(app)
            response = client.post(
                "/api/v1/tasks",
                json={
                    "user_id": "user-123",
                    "prompt": "Continue conversation",
                    "session_id": "existing-session",
                    "config": {
                        "model": "claude-3",
                    },
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["session_id"] == "existing-session"

    def test_get_task_status_success(self) -> None:
        """Test successful task status retrieval."""
        from app.main import app

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "task_id": "task-123",
            "status": "running",
            "progress": 50,
        }

        mock_service = MagicMock()
        mock_service.get_task_status.return_value = mock_result

        with _service_override(app, mock_service):
            client = TestClient(app)
            response = client.get("/api/v1/tasks/task-123")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["task_id"] == "task-123"
            mock_service.get_task_status.assert_called_once_with("task-123")

    def test_get_task_status_by_session_success(self) -> None:
        """Test successful task status retrieval by session ID."""
        from app.main import app

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "session_id": "session-123",
            "status": "completed",
            "task_ids": ["task-1", "task-2"],
        }

        mock_service = MagicMock()
        mock_service.get_session_status = AsyncMock(return_value=mock_result)

        with _service_override(app, mock_service):
            client = TestClient(app)
            response = client.get("/api/v1/tasks/session/session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["session_id"] == "session-123"
            mock_service.get_session_status.assert_called_once_with("session-123")


if __name__ == "__main__":
    unittest.main()
