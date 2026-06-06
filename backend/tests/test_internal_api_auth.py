from datetime import UTC, datetime
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Importing app.api.v1 currently imports modules with S3 clients at module load.
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")

from app.core.settings import get_settings

get_settings.cache_clear()

from app.api.v1 import (  # noqa: E402
    callback,
    internal_mcp_transitions,
    internal_permission_audit,
    internal_runs,
    internal_scheduled_tasks,
    internal_user_input_requests,
    runs,
)
from app.core.deps import get_db  # noqa: E402
from app.core.errors.exception_handlers import setup_exception_handlers  # noqa: E402
from app.schemas.callback import CallbackResponse, CallbackStatus  # noqa: E402
from app.schemas.scheduled_task import ScheduledTaskDispatchResponse  # noqa: E402
from app.schemas.user_input_request import UserInputRequestResponse  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    setup_exception_handlers(app, debug=False)
    app.include_router(runs.router)
    app.include_router(internal_runs.router)
    app.include_router(internal_mcp_transitions.router)
    app.include_router(internal_permission_audit.router)
    app.include_router(internal_scheduled_tasks.router)
    app.include_router(internal_user_input_requests.router)
    app.include_router(callback.router)
    return TestClient(app)


def _settings():
    return SimpleNamespace(internal_api_token="internal-token")


def _user_input_response() -> UserInputRequestResponse:
    return UserInputRequestResponse(
        id=uuid.UUID("00000000-0000-0000-0000-000000000101"),
        session_id=uuid.UUID("00000000-0000-0000-0000-000000000102"),
        tool_name="AskUserQuestion",
        tool_input={"question": "Proceed?"},
        status="pending",
        answers=None,
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
        answered_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_run_claim_requires_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/runs/claim",
            json={"worker_id": "worker-1", "lease_seconds": 30},
        )

    assert response.status_code == 403


def test_run_start_requires_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/runs/00000000-0000-0000-0000-000000000001/start",
            json={"worker_id": "worker-1"},
        )

    assert response.status_code == 403


def test_run_fail_requires_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/runs/00000000-0000-0000-0000-000000000001/fail",
            json={"worker_id": "worker-1", "error_message": "dispatch failed"},
        )

    assert response.status_code == 403


def test_run_claim_requires_service_identity():
    """Run claim with valid token but missing service header fails."""
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.runs.run_service.claim_next_run", return_value=None):
            response = client.post(
                "/runs/claim",
                json={"worker_id": "worker-1", "lease_seconds": 30},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]


def test_run_claim_accepts_valid_token_and_service():
    """Run claim with valid token and executor_manager service succeeds."""
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.runs.run_service.claim_next_run", return_value=None):
            response = client.post(
                "/runs/claim",
                json={"worker_id": "worker-1", "lease_seconds": 30},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200


def test_run_start_requires_service_identity():
    """Run start with valid token but missing service header fails."""
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.runs.run_service.start_run") as mock:
            mock.return_value = SimpleNamespace(
                id="00000000-0000-0000-0000-000000000001",
                session_id="session-1",
                status="running",
                worker_id="worker-1",
            )
            response = client.post(
                "/runs/00000000-0000-0000-0000-000000000001/start",
                json={"worker_id": "worker-1"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]


def test_run_fail_requires_service_identity():
    """Run fail with valid token but missing service header fails."""
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.runs.run_service.fail_run") as mock:
            mock.return_value = SimpleNamespace(
                id="00000000-0000-0000-0000-000000000001",
                session_id="session-1",
                status="failed",
                worker_id="worker-1",
            )
            response = client.post(
                "/runs/00000000-0000-0000-0000-000000000001/fail",
                json={"worker_id": "worker-1", "error_message": "dispatch failed"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]


def test_internal_run_metadata_requires_service_identity():
    """Run metadata update with valid token but missing service header fails."""
    client = _client()
    client.app.dependency_overrides[get_db] = lambda: MagicMock()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_runs.RunRepository.get_by_id",
            return_value=None,
        ):
            response = client.patch(
                "/internal/runs/00000000-0000-0000-0000-000000000001/metadata",
                json={"config_layers": {"source": "resolver"}},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]


def test_internal_run_metadata_accepts_valid_token_and_service():
    """Run metadata update accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    mock_run = SimpleNamespace(
        permission_policy_snapshot=None,
        resolved_hook_specs=None,
        config_layers=None,
    )

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_runs.RunRepository.get_by_id",
            return_value=mock_run,
        ):
            response = client.patch(
                "/internal/runs/00000000-0000-0000-0000-000000000001/metadata",
                json={"config_layers": {"source": "resolver"}},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    assert mock_run.config_layers == {"source": "resolver"}
    db.flush.assert_called_once()
    db.commit.assert_called_once()


def test_internal_mcp_transition_requires_service_identity():
    """MCP transition with valid token but missing service header fails."""
    client = _client()
    client.app.dependency_overrides[get_db] = lambda: MagicMock()
    payload = {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000002",
        "server_name": "filesystem",
        "to_state": "connected",
        "event_source": "executor_manager",
    }

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_mcp_transitions.McpConnectionService"
        ) as service_cls:
            response = client.post(
                "/internal/mcp-transitions",
                json=payload,
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    service_cls.assert_not_called()


def test_internal_mcp_transition_accepts_valid_token_and_service():
    """MCP transition accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    payload = {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000002",
        "server_name": "filesystem",
        "to_state": "connected",
        "event_source": "executor_manager",
    }

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_mcp_transitions.McpConnectionService"
        ) as service_cls:
            response = client.post(
                "/internal/mcp-transitions",
                json=payload,
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    service_cls.return_value.record_transition.assert_called_once()
    db.commit.assert_called_once()


def test_internal_permission_audit_requires_service_identity():
    """Permission audit with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    payload = {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000002",
        "tool_name": "Read",
        "policy_action": "allow",
    }

    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/internal/permission-audit",
            json=payload,
            headers={"X-Internal-Token": "internal-token"},
        )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_internal_permission_audit_accepts_valid_token_and_service():
    """Permission audit accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    payload = {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000002",
        "tool_name": "Read",
        "policy_action": "allow",
    }

    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/internal/permission-audit",
            json=payload,
            headers={
                "X-Internal-Token": "internal-token",
                "X-Internal-Service": "executor_manager",
            },
        )

    assert response.status_code == 200
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_internal_scheduled_task_dispatch_requires_service_identity():
    """Scheduled dispatch with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_scheduled_tasks.scheduled_task_service.dispatch_due",
            return_value=ScheduledTaskDispatchResponse(dispatched=0),
        ) as dispatch_due:
            response = client.post(
                "/internal/scheduled-tasks/dispatch-due",
                json={"limit": 10},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    dispatch_due.assert_not_called()


def test_internal_scheduled_task_dispatch_accepts_valid_token_and_service():
    """Scheduled dispatch accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_scheduled_tasks.scheduled_task_service.dispatch_due",
            return_value=ScheduledTaskDispatchResponse(dispatched=1),
        ) as dispatch_due:
            response = client.post(
                "/internal/scheduled-tasks/dispatch-due",
                json={"limit": 10},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    dispatch_due.assert_called_once_with(db, limit=10)


def test_internal_user_input_create_requires_service_identity():
    """User input request creation with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    payload = {
        "session_id": "00000000-0000-0000-0000-000000000102",
        "tool_name": "AskUserQuestion",
        "tool_input": {"question": "Proceed?"},
    }

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_user_input_requests.user_input_service.create_request",
            return_value=_user_input_response(),
        ) as create_request:
            response = client.post(
                "/internal/user-input-requests",
                json=payload,
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    create_request.assert_not_called()


def test_internal_user_input_create_accepts_valid_token_and_service():
    """User input request creation accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    payload = {
        "session_id": "00000000-0000-0000-0000-000000000102",
        "tool_name": "AskUserQuestion",
        "tool_input": {"question": "Proceed?"},
    }

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_user_input_requests.user_input_service.create_request",
            return_value=_user_input_response(),
        ) as create_request:
            response = client.post(
                "/internal/user-input-requests",
                json=payload,
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    create_request.assert_called_once()
    assert create_request.call_args.args[0] is db


def test_internal_user_input_get_requires_service_identity():
    """User input request retrieval with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_user_input_requests.user_input_service.get_request",
            return_value=_user_input_response(),
        ) as get_request:
            response = client.get(
                "/internal/user-input-requests/00000000-0000-0000-0000-000000000101",
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    get_request.assert_not_called()


def test_internal_user_input_get_accepts_valid_token_and_service():
    """User input request retrieval accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_user_input_requests.user_input_service.get_request",
            return_value=_user_input_response(),
        ) as get_request:
            response = client.get(
                "/internal/user-input-requests/00000000-0000-0000-0000-000000000101",
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    get_request.assert_called_once_with(
        db, request_id="00000000-0000-0000-0000-000000000101"
    )


def test_callback_requires_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/callback",
            json={
                "session_id": "session-1",
                "time": datetime.now(UTC).isoformat(),
                "status": "running",
                "progress": 10,
            },
        )

    assert response.status_code == 403


def test_callback_requires_service_identity():
    """Backend callback with valid token but missing service header fails."""
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.callback.callback_service.process_agent_callback") as fn:
            fn.return_value = CallbackResponse(
                session_id="session-1",
                status="running",
                callback_status=CallbackStatus.RUNNING,
                message=None,
            )
            response = client.post(
                "/callback",
                json={
                    "session_id": "session-1",
                    "time": datetime.now(UTC).isoformat(),
                    "status": "running",
                    "progress": 10,
                },
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    fn.assert_not_called()


def test_callback_accepts_valid_token_and_service():
    """Backend callback accepts executor_manager service identity."""
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.callback.callback_service.process_agent_callback") as fn:
            fn.return_value = CallbackResponse(
                session_id="session-1",
                status="running",
                callback_status=CallbackStatus.RUNNING,
                message=None,
            )
            response = client.post(
                "/callback",
                json={
                    "session_id": "session-1",
                    "time": datetime.now(UTC).isoformat(),
                    "status": "running",
                    "progress": 10,
                },
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    fn.assert_called_once()
