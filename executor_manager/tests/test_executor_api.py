"""Tests for app/api/v1/executor.py."""

import typing
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.schemas.task import ContainerInfoResponse, ContainerStatsResponse


def _make_container_stats(
    *,
    total_active: int = 1,
    persistent_containers: int = 1,
    ephemeral_containers: int = 0,
) -> ContainerStatsResponse:
    return ContainerStatsResponse(
        total_active=total_active,
        persistent_containers=persistent_containers,
        ephemeral_containers=ephemeral_containers,
        containers=[
            ContainerInfoResponse(
                container_id="container-1",
                name="executor-1",
                status="running",
                mode="persistent",
            )
        ]
        if total_active
        else [],
    )


def test_executor_routes_use_container_pool_dependency_override() -> None:
    from app.api.v1 import executor
    from app.main import app

    mock_pool = MagicMock()
    mock_pool.get_container_stats.return_value = _make_container_stats()

    app.dependency_overrides[executor.get_container_pool] = lambda: mock_pool
    try:
        with patch(
            "app.api.v1.executor.TaskDispatcher.get_container_pool",
            side_effect=AssertionError("route should use pool override"),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/executor/load")
    finally:
        app.dependency_overrides.pop(executor.get_container_pool, None)

    assert response.status_code == 200
    assert response.json()["data"]["total_active"] == 1
    mock_pool.get_container_stats.assert_called_once_with()


def test_executor_container_pool_stats_port_returns_response_dto() -> None:
    """Verify executor load route port returns ContainerStatsResponse, not Any."""
    from app.api.v1.executor import ExecutorContainerPool

    hints = typing.get_type_hints(ExecutorContainerPool.get_container_stats)
    return_hint = hints.get("return")

    assert return_hint is ContainerStatsResponse
    assert "Any" not in str(return_hint)


class TestExecutorEndpoints(unittest.TestCase):
    """Test /api/v1/executor endpoints."""

    def test_cancel_task_success(self) -> None:
        """Test successful task cancellation."""
        from app.main import app

        mock_pool = MagicMock()
        mock_pool.cancel_task = AsyncMock()

        with patch(
            "app.api.v1.executor.TaskDispatcher.get_container_pool",
            return_value=mock_pool,
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/executor/cancel",
                json={"session_id": "session-123"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["session_id"] == "session-123"
            assert data["data"]["status"] == "canceled"
            mock_pool.cancel_task.assert_called_once_with("session-123")

    def test_delete_container_success(self) -> None:
        """Test successful container deletion."""
        from app.main import app

        mock_pool = MagicMock()
        mock_pool.delete_container = AsyncMock()

        with patch(
            "app.api.v1.executor.TaskDispatcher.get_container_pool",
            return_value=mock_pool,
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/executor/delete",
                json={"container_id": "container-456"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["container_id"] == "container-456"
            assert data["data"]["status"] == "deleted"
            mock_pool.delete_container.assert_called_once_with("container-456")

    def test_get_executor_load_success(self) -> None:
        """Test successful load stats retrieval."""
        from app.main import app

        mock_pool = MagicMock()
        mock_pool.get_container_stats.return_value = _make_container_stats(
            total_active=5,
            persistent_containers=3,
            ephemeral_containers=2,
        )

        with patch(
            "app.api.v1.executor.TaskDispatcher.get_container_pool",
            return_value=mock_pool,
        ):
            client = TestClient(app)
            response = client.get("/api/v1/executor/load")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["total_active"] == 5
            assert data["data"]["persistent_containers"] == 3
            assert data["data"]["ephemeral_containers"] == 2
            assert data["data"]["containers"][0]["container_id"] == "container-1"
            mock_pool.get_container_stats.assert_called_once()

    def test_cancel_task_with_empty_session_id(self) -> None:
        """Test cancel task with empty session_id."""
        from app.main import app

        mock_pool = MagicMock()
        mock_pool.cancel_task = AsyncMock()

        with patch(
            "app.api.v1.executor.TaskDispatcher.get_container_pool",
            return_value=mock_pool,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/executor/cancel",
                json={"session_id": ""},
            )

            # Should still work (validation is on the model)
            # The endpoint calls cancel_task with empty string
            assert response.status_code == 200

    def test_get_executor_load_empty_stats(self) -> None:
        """Test load stats when no containers."""
        from app.main import app

        mock_pool = MagicMock()
        mock_pool.get_container_stats.return_value = _make_container_stats(
            total_active=0,
            persistent_containers=0,
            ephemeral_containers=0,
        )

        with patch(
            "app.api.v1.executor.TaskDispatcher.get_container_pool",
            return_value=mock_pool,
        ):
            client = TestClient(app)
            response = client.get("/api/v1/executor/load")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"] == {
                "total_active": 0,
                "persistent_containers": 0,
                "ephemeral_containers": 0,
                "containers": [],
            }


if __name__ == "__main__":
    unittest.main()
