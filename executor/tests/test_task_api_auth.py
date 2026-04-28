import hashlib
import hmac
import time
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


def _task_lease_headers(
    *,
    session_id: str = "session-123",
    run_id: str | None = "run-456",
    secret: str = "executor-secret",
    expires_at: int | None = None,
) -> dict[str, str]:
    expires_at = expires_at or int(time.time()) + 60
    payload = f"{session_id}\n{run_id or ''}\n{expires_at}".encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {
        "X-Poco-Task-Lease-Expires-At": str(expires_at),
        "X-Poco-Task-Lease-Signature": signature,
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


def test_execute_requires_task_lease(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    response = TestClient(app).post(
        "/v1/tasks/execute",
        json=_task_payload(),
        headers={"Authorization": "Bearer executor-secret"},
    )

    assert response.status_code == 403


def test_execute_rejects_invalid_task_lease(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    headers = {
        "Authorization": "Bearer executor-secret",
        **_task_lease_headers(),
        "X-Poco-Task-Lease-Signature": "bad-signature",
    }

    response = TestClient(app).post(
        "/v1/tasks/execute",
        json=_task_payload(),
        headers=headers,
    )

    assert response.status_code == 403


def test_execute_rejects_expired_task_lease(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    headers = {
        "Authorization": "Bearer executor-secret",
        **_task_lease_headers(expires_at=int(time.time()) - 1),
    }

    response = TestClient(app).post(
        "/v1/tasks/execute",
        json=_task_payload(),
        headers=headers,
    )

    assert response.status_code == 403


def test_execute_accepts_executor_token_and_task_lease(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    executor = MagicMock()
    executor.workspace.root_path = tmp_path
    executor.execute = AsyncMock()

    with patch("app.api.v1.task.AgentExecutor", return_value=executor):
        with patch("app.api.v1.task.HookRegistry") as registry_cls:
            with patch("app.api.v1.task.UserInputClient") as user_input_cls:
                with patch("app.api.v1.task.ComputerClient") as computer_cls:
                    user_input_cls.resolve_base_url.return_value = (
                        "http://executor-manager"
                    )
                    registry = registry_cls.return_value
                    registry.default_specs.return_value = []
                    registry.build.return_value = []

                    response = TestClient(app).post(
                        "/v1/tasks/execute",
                        json=_task_payload(),
                        headers={
                            "Authorization": "Bearer executor-secret",
                            **_task_lease_headers(),
                        },
                    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "session_id": "session-123"}
    user_input_cls.assert_called_once_with(
        base_url="http://executor-manager",
        callback_token="executor-secret",
    )
    computer_cls.assert_called_once_with(
        base_url="http://executor-manager",
        callback_token="executor-secret",
    )
    executor.execute.assert_awaited_once()
