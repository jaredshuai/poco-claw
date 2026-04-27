from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _task_payload() -> dict:
    return {
        "session_id": "session-123",
        "run_id": "run-456",
        "prompt": "Hello",
        "callback_url": "http://executor-manager/api/v1/callback",
        "callback_token": "executor-secret",
        "config": {},
    }


def test_execute_requires_executor_token(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    response = TestClient(app).post("/v1/tasks/execute", json=_task_payload())

    assert response.status_code == 403


def test_execute_rejects_invalid_executor_token(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    response = TestClient(app).post(
        "/v1/tasks/execute",
        json=_task_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 403


def test_execute_accepts_executor_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    executor = MagicMock()
    executor.workspace.root_path = tmp_path
    executor.execute = AsyncMock()

    with patch("app.api.v1.task.AgentExecutor", return_value=executor):
        with patch("app.api.v1.task.HookRegistry") as registry_cls:
            registry = registry_cls.return_value
            registry.default_specs.return_value = []
            registry.build.return_value = []

            response = TestClient(app).post(
                "/v1/tasks/execute",
                json=_task_payload(),
                headers={"Authorization": "Bearer executor-secret"},
            )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "session_id": "session-123"}
    executor.execute.assert_awaited_once()
