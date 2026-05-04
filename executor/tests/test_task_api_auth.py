import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.deps import require_executor_task_lease
from app.main import app


TASK_LEASE_BODY_DIGEST_HEADER = "X-Poco-Task-Lease-Body-SHA256"


@pytest.fixture(autouse=True)
def _clear_task_lease_secret(monkeypatch) -> None:
    monkeypatch.delenv("EXECUTOR_TASK_LEASE_SECRET", raising=False)


def _task_payload() -> dict:
    return {
        "session_id": "session-123",
        "run_id": "run-456",
        "prompt": "Hello",
        "callback_url": "http://executor-manager/api/v1/callback",
        "callback_token": "executor-secret",
        "config": {},
    }


def _compute_body_digest(body: bytes) -> str:
    """Compute SHA-256 digest of request body bytes."""
    return hashlib.sha256(body).hexdigest()


def _task_lease_headers(
    *,
    session_id: str = "session-123",
    run_id: str | None = "run-456",
    secret: str = "executor-secret",
    expires_at: int | None = None,
    body_digest: str | None = None,
) -> dict[str, str]:
    expires_at = expires_at or int(time.time()) + 60
    # Include body digest in signature payload if provided
    if body_digest:
        payload = f"{session_id}\n{run_id or ''}\n{expires_at}\n{body_digest}".encode()
    else:
        payload = f"{session_id}\n{run_id or ''}\n{expires_at}".encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    headers = {
        "X-Poco-Task-Lease-Expires-At": str(expires_at),
        "X-Poco-Task-Lease-Signature": signature,
    }
    if body_digest:
        headers[TASK_LEASE_BODY_DIGEST_HEADER] = body_digest
    return headers


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


def test_task_lease_validation_uses_injected_clock(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    clock = MagicMock()
    clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
    body = b'{"test": "data"}'
    body_digest = _compute_body_digest(body)
    headers = _task_lease_headers(expires_at=1300, body_digest=body_digest)

    require_executor_task_lease(
        session_id="session-123",
        run_id="run-456",
        body=body,
        expires_at_header=headers["X-Poco-Task-Lease-Expires-At"],
        signature_header=headers["X-Poco-Task-Lease-Signature"],
        body_digest_header=headers[TASK_LEASE_BODY_DIGEST_HEADER],
        clock=clock,
    )

    clock.now_utc.assert_called_once_with()


def test_task_lease_validation_rejects_expired_with_injected_clock(monkeypatch) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    clock = MagicMock()
    clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
    body = b'{"test": "data"}'
    body_digest = _compute_body_digest(body)
    headers = _task_lease_headers(expires_at=999, body_digest=body_digest)

    with pytest.raises(HTTPException) as exc:
        require_executor_task_lease(
            session_id="session-123",
            run_id="run-456",
            body=body,
            expires_at_header=headers["X-Poco-Task-Lease-Expires-At"],
            signature_header=headers["X-Poco-Task-Lease-Signature"],
            body_digest_header=headers[TASK_LEASE_BODY_DIGEST_HEADER],
            clock=clock,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Executor task lease expired"
    clock.now_utc.assert_called_once_with()


def test_execute_rejects_callback_token_signature_when_task_lease_secret_is_set(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "callback-token")
    monkeypatch.setenv("EXECUTOR_TASK_LEASE_SECRET", "lease-secret")
    headers = {
        "Authorization": "Bearer callback-token",
        **_task_lease_headers(secret="callback-token"),
    }

    response = TestClient(app).post(
        "/v1/tasks/execute",
        json={**_task_payload(), "callback_token": "callback-token"},
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

    payload = _task_payload()
    body = json.dumps(payload).encode()
    body_digest = _compute_body_digest(body)

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
                        content=body,
                        headers={
                            "Authorization": "Bearer executor-secret",
                            "Content-Type": "application/json",
                            **_task_lease_headers(body_digest=body_digest),
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


def test_execute_accepts_dedicated_task_lease_secret(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CALLBACK_TOKEN", "callback-token")
    monkeypatch.setenv("EXECUTOR_TASK_LEASE_SECRET", "lease-secret")
    executor = MagicMock()
    executor.workspace.root_path = tmp_path
    executor.execute = AsyncMock()

    payload = {**_task_payload(), "callback_token": "callback-token"}
    body = json.dumps(payload).encode()
    body_digest = _compute_body_digest(body)

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
                        content=body,
                        headers={
                            "Authorization": "Bearer callback-token",
                            "Content-Type": "application/json",
                            **_task_lease_headers(
                                secret="lease-secret", body_digest=body_digest
                            ),
                        },
                    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "session_id": "session-123"}
    user_input_cls.assert_called_once_with(
        base_url="http://executor-manager",
        callback_token="callback-token",
    )
    computer_cls.assert_called_once_with(
        base_url="http://executor-manager",
        callback_token="callback-token",
    )
    executor.execute.assert_awaited_once()


def test_execute_rejects_missing_body_digest_header(monkeypatch) -> None:
    """Executor must reject requests when body digest header is missing."""
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")
    payload = _task_payload()
    body = json.dumps(payload).encode()
    # Provide lease headers without body digest
    headers = {
        "Authorization": "Bearer executor-secret",
        "Content-Type": "application/json",
        **_task_lease_headers(),  # No body digest
    }

    response = TestClient(app).post(
        "/v1/tasks/execute",
        content=body,
        headers=headers,
    )

    assert response.status_code == 403


def test_execute_rejects_tampered_body(monkeypatch, tmp_path: Path) -> None:
    """Executor must reject when body digest doesn't match actual body."""
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    original_payload = _task_payload()
    original_body = json.dumps(original_payload).encode()
    original_digest = _compute_body_digest(original_body)

    # Tampered payload with different prompt
    tampered_payload = {**original_payload, "prompt": "Malicious prompt"}
    tampered_body = json.dumps(tampered_payload).encode()

    # Lease headers signed for original body
    headers = {
        "Authorization": "Bearer executor-secret",
        "Content-Type": "application/json",
        **_task_lease_headers(body_digest=original_digest),
    }

    response = TestClient(app).post(
        "/v1/tasks/execute",
        content=tampered_body,
        headers=headers,
    )

    assert response.status_code == 403


def test_execute_rejects_signature_for_different_body_digest(monkeypatch) -> None:
    """Executor must reject when signature was made for different body digest."""
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    payload = _task_payload()
    body = json.dumps(payload).encode()
    actual_digest = _compute_body_digest(body)

    # Signature made for different (fake) digest
    fake_digest = "0" * 64
    headers = {
        "Authorization": "Bearer executor-secret",
        "Content-Type": "application/json",
        **_task_lease_headers(body_digest=fake_digest),
        # Override the digest header with actual digest (mismatch with signature)
        TASK_LEASE_BODY_DIGEST_HEADER: actual_digest,
    }

    response = TestClient(app).post(
        "/v1/tasks/execute",
        content=body,
        headers=headers,
    )

    assert response.status_code == 403


def test_execute_accepts_valid_body_digest(monkeypatch, tmp_path: Path) -> None:
    """Executor must accept when body digest matches and signature is valid."""
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    payload = _task_payload()
    body = json.dumps(payload).encode()
    body_digest = _compute_body_digest(body)

    executor = MagicMock()
    executor.workspace.root_path = tmp_path
    executor.execute = AsyncMock()

    with patch("app.api.v1.task.AgentExecutor", return_value=executor):
        with patch("app.api.v1.task.HookRegistry") as registry_cls:
            with patch("app.api.v1.task.UserInputClient") as user_input_cls:
                with patch("app.api.v1.task.ComputerClient"):
                    user_input_cls.resolve_base_url.return_value = (
                        "http://executor-manager"
                    )
                    registry = registry_cls.return_value
                    registry.default_specs.return_value = []
                    registry.build.return_value = []

                    response = TestClient(app).post(
                        "/v1/tasks/execute",
                        content=body,
                        headers={
                            "Authorization": "Bearer executor-secret",
                            "Content-Type": "application/json",
                            **_task_lease_headers(body_digest=body_digest),
                        },
                    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "session_id": "session-123"}


def test_execute_returns_422_for_invalid_task_run_body(monkeypatch) -> None:
    """FastAPI must validate TaskRun body and return 422 for invalid JSON."""
    monkeypatch.setenv("CALLBACK_TOKEN", "executor-secret")

    # Create a body missing required field "prompt"
    invalid_payload = {
        "session_id": "session-123",
        "run_id": "run-456",
        # Missing "prompt" - required field
        "callback_url": "http://executor-manager/api/v1/callback",
        "callback_token": "executor-secret",
        "config": {},
    }
    body = json.dumps(invalid_payload).encode()
    body_digest = _compute_body_digest(body)

    response = TestClient(app).post(
        "/v1/tasks/execute",
        content=body,
        headers={
            "Authorization": "Bearer executor-secret",
            "Content-Type": "application/json",
            **_task_lease_headers(body_digest=body_digest),
        },
    )

    # FastAPI should return 422 Unprocessable Entity for validation errors
    assert response.status_code == 422
