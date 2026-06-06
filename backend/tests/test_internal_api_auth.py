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
    internal_env_vars,
    internal_memories,
    internal_mcp_config,
    internal_mcp_transitions,
    internal_permission_audit,
    internal_plugin_config,
    internal_runs,
    internal_scheduled_tasks,
    internal_skill_config,
    internal_skills,
    internal_slash_commands,
    internal_user_input_requests,
    runs,
)
from app.core.deps import get_db, get_user_id_by_session_id  # noqa: E402
from app.core.errors.exception_handlers import setup_exception_handlers  # noqa: E402
from app.schemas.callback import CallbackResponse, CallbackStatus  # noqa: E402
from app.schemas.env_var import SystemEnvVarResponse  # noqa: E402
from app.schemas.memory import MemoryCreateJobEnqueueResponse  # noqa: E402
from app.schemas.scheduled_task import ScheduledTaskDispatchResponse  # noqa: E402
from app.schemas.user_input_request import UserInputRequestResponse  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    setup_exception_handlers(app, debug=False)
    app.include_router(runs.router)
    app.include_router(internal_runs.router)
    app.include_router(internal_env_vars.router)
    app.include_router(internal_memories.router)
    app.include_router(internal_mcp_config.router)
    app.include_router(internal_mcp_transitions.router)
    app.include_router(internal_permission_audit.router)
    app.include_router(internal_plugin_config.router)
    app.include_router(internal_scheduled_tasks.router)
    app.include_router(internal_skill_config.router)
    app.include_router(internal_skills.router)
    app.include_router(internal_slash_commands.router)
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


def _system_env_var_response() -> SystemEnvVarResponse:
    return SystemEnvVarResponse(
        id=1,
        user_id="system",
        key="SYSTEM_TOKEN",
        value="secret",
        description="System token",
        scope="system",
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


def test_internal_mcp_config_resolve_requires_service_identity():
    """MCP config resolve with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_mcp_config.service.resolve_user_mcp_config",
            return_value={"servers": []},
        ) as resolve_user_mcp_config:
            response = client.post(
                "/internal/mcp-config/resolve",
                json={"server_ids": [1, 2]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    resolve_user_mcp_config.assert_not_called()


def test_internal_mcp_config_resolve_accepts_valid_token_and_service():
    """MCP config resolve accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_mcp_config.service.resolve_user_mcp_config",
            return_value={"servers": []},
        ) as resolve_user_mcp_config:
            response = client.post(
                "/internal/mcp-config/resolve",
                json={"server_ids": [1, 2]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 200
    resolve_user_mcp_config.assert_called_once_with(
        db=db,
        user_id="user-1",
        server_ids=[1, 2],
    )


def test_internal_skill_config_resolve_requires_service_identity():
    """Skill config resolve with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_skill_config.service.resolve_user_skill_files",
            return_value={"skills": []},
        ) as resolve_user_skill_files:
            response = client.post(
                "/internal/skill-config/resolve",
                json={"skill_ids": [1, 2]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    resolve_user_skill_files.assert_not_called()


def test_internal_skill_config_resolve_accepts_valid_token_and_service():
    """Skill config resolve accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_skill_config.service.resolve_user_skill_files",
            return_value={"skills": []},
        ) as resolve_user_skill_files:
            response = client.post(
                "/internal/skill-config/resolve",
                json={"skill_ids": [1, 2]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 200
    resolve_user_skill_files.assert_called_once_with(
        db=db,
        user_id="user-1",
        skill_ids=[1, 2],
    )


def test_internal_plugin_config_resolve_requires_service_identity():
    """Plugin config resolve with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_plugin_config.service.resolve_user_plugin_files",
            return_value={"plugins": []},
        ) as resolve_user_plugin_files:
            response = client.post(
                "/internal/plugin-config/resolve",
                json={"plugin_ids": [1, 2]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    resolve_user_plugin_files.assert_not_called()


def test_internal_plugin_config_resolve_accepts_valid_token_and_service():
    """Plugin config resolve accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_plugin_config.service.resolve_user_plugin_files",
            return_value={"plugins": []},
        ) as resolve_user_plugin_files:
            response = client.post(
                "/internal/plugin-config/resolve",
                json={"plugin_ids": [1, 2]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 200
    resolve_user_plugin_files.assert_called_once_with(
        db=db,
        user_id="user-1",
        plugin_ids=[1, 2],
    )


def test_internal_slash_commands_resolve_requires_service_identity():
    """Slash command resolve with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_slash_commands.service.resolve_user_commands",
            return_value={"cmd": "content"},
        ) as resolve_user_commands:
            response = client.post(
                "/internal/slash-commands/resolve",
                json={"names": ["cmd"], "skill_names": ["skill"]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    resolve_user_commands.assert_not_called()


def test_internal_slash_commands_resolve_accepts_valid_token_and_service():
    """Slash command resolve accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_slash_commands.service.resolve_user_commands",
            return_value={"cmd": "content"},
        ) as resolve_user_commands:
            response = client.post(
                "/internal/slash-commands/resolve",
                json={"names": ["cmd"], "skill_names": ["skill"]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                    "X-User-Id": "user-1",
                },
            )

    assert response.status_code == 200
    resolve_user_commands.assert_called_once_with(
        db,
        user_id="user-1",
        names=["cmd"],
        skill_names=["skill"],
    )


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


def test_internal_skill_submit_requires_service_identity():
    """Skill submission with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"
    payload = {
        "folder_path": "skills/demo",
        "skill_name": "demo",
        "workspace_files_prefix": "workspace/session-1",
    }
    session_id = "00000000-0000-0000-0000-000000000201"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with (
            patch(
                "app.api.v1.internal_skills.SessionRepository.get_by_id",
                return_value=SimpleNamespace(id=session_id),
            ),
            patch(
                "app.api.v1.internal_skills.pending_skill_creation_service"
                ".submit_from_workspace",
                return_value=SimpleNamespace(
                    id=uuid.UUID("00000000-0000-0000-0000-000000000202"),
                    status="pending",
                ),
            ) as submit_from_workspace,
        ):
            response = client.post(
                "/internal/skills/submit-from-workspace",
                params={"session_id": session_id},
                json=payload,
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    submit_from_workspace.assert_not_called()
    db.commit.assert_not_called()


def test_internal_skill_submit_accepts_valid_token_and_service():
    """Skill submission accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"
    payload = {
        "folder_path": "skills/demo",
        "skill_name": "demo",
        "workspace_files_prefix": "workspace/session-1",
    }
    session_id = "00000000-0000-0000-0000-000000000201"
    session = SimpleNamespace(id=session_id)
    pending = SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000202"),
        status="pending",
    )

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with (
            patch(
                "app.api.v1.internal_skills.SessionRepository.get_by_id",
                return_value=session,
            ),
            patch(
                "app.api.v1.internal_skills.pending_skill_creation_service"
                ".submit_from_workspace",
                return_value=pending,
            ) as submit_from_workspace,
        ):
            response = client.post(
                "/internal/skills/submit-from-workspace",
                params={"session_id": session_id},
                json=payload,
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    submit_from_workspace.assert_called_once_with(
        db,
        user_id="user-1",
        session=session,
        folder_path="skills/demo",
        skill_name="demo",
        workspace_files_prefix="workspace/session-1",
    )
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(pending)


def test_internal_memory_create_requires_service_identity():
    """Memory creation with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_create_job_service.enqueue_create",
            return_value=MemoryCreateJobEnqueueResponse(
                job_id=uuid.UUID("00000000-0000-0000-0000-000000000301"),
                status="queued",
            ),
        ) as enqueue_create:
            response = client.post(
                "/internal/memories",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                json={"messages": [{"role": "user", "content": "remember this"}]},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    enqueue_create.assert_not_called()


def test_internal_memory_create_accepts_valid_token_and_service():
    """Memory creation accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"
    job_id = uuid.UUID("00000000-0000-0000-0000-000000000301")
    result = MemoryCreateJobEnqueueResponse(job_id=job_id, status="queued")

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with (
            patch(
                "app.api.v1.internal_memories.memory_create_job_service.enqueue_create",
                return_value=result,
            ) as enqueue_create,
            patch(
                "app.api.v1.internal_memories.memory_create_job_service"
                ".process_create_job",
            ) as process_create_job,
        ):
            response = client.post(
                "/internal/memories",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                json={"messages": [{"role": "user", "content": "remember this"}]},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    enqueue_create.assert_called_once()
    assert enqueue_create.call_args.args[0] is db
    assert enqueue_create.call_args.kwargs["user_id"] == "user-1"
    process_create_job.assert_called_once_with(job_id)


def test_internal_memory_update_requires_service_identity():
    """Memory update with valid token but missing service header fails."""
    client = _client()
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_service.update_memory",
            return_value={"id": "mem-1", "content": "updated"},
        ) as update_memory:
            response = client.put(
                "/internal/memories/mem-1",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                json={"text": "updated"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    update_memory.assert_not_called()


def test_internal_memory_update_accepts_valid_token_and_service():
    """Memory update accepts executor_manager service identity."""
    client = _client()
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_service.update_memory",
            return_value={"id": "mem-1", "content": "updated"},
        ) as update_memory:
            response = client.put(
                "/internal/memories/mem-1",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                json={"text": "updated"},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    update_memory.assert_called_once_with(
        memory_id="mem-1",
        user_id="user-1",
        text="updated",
    )


def test_internal_memory_delete_requires_service_identity():
    """Memory deletion with valid token but missing service header fails."""
    client = _client()
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_service.delete_memory"
        ) as delete_memory:
            response = client.delete(
                "/internal/memories/mem-1",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    delete_memory.assert_not_called()


def test_internal_memory_delete_accepts_valid_token_and_service():
    """Memory deletion accepts executor_manager service identity."""
    client = _client()
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_service.delete_memory"
        ) as delete_memory:
            response = client.delete(
                "/internal/memories/mem-1",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    delete_memory.assert_called_once_with(memory_id="mem-1", user_id="user-1")


def test_internal_memory_delete_all_requires_service_identity():
    """Memory bulk deletion with valid token but missing service header fails."""
    client = _client()
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_service.delete_all_memories"
        ) as delete_all_memories:
            response = client.delete(
                "/internal/memories",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    delete_all_memories.assert_not_called()


def test_internal_memory_delete_all_accepts_valid_token_and_service():
    """Memory bulk deletion accepts executor_manager service identity."""
    client = _client()
    client.app.dependency_overrides[get_user_id_by_session_id] = lambda: "user-1"

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_memories.memory_service.delete_all_memories"
        ) as delete_all_memories:
            response = client.delete(
                "/internal/memories",
                params={"session_id": "00000000-0000-0000-0000-000000000302"},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    delete_all_memories.assert_called_once_with(user_id="user-1")


def test_internal_system_env_var_create_requires_service_identity():
    """System env-var creation with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_env_vars.env_var_service.create_system_env_var",
            return_value=_system_env_var_response(),
        ) as create_system_env_var:
            response = client.post(
                "/internal/system-env-vars",
                json={"key": "SYSTEM_TOKEN", "value": "secret"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    create_system_env_var.assert_not_called()


def test_internal_system_env_var_create_accepts_valid_token_and_service():
    """System env-var creation accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_env_vars.env_var_service.create_system_env_var",
            return_value=_system_env_var_response(),
        ) as create_system_env_var:
            response = client.post(
                "/internal/system-env-vars",
                json={"key": "SYSTEM_TOKEN", "value": "secret"},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    create_system_env_var.assert_called_once()
    assert create_system_env_var.call_args.args[0] is db


def test_internal_system_env_var_update_requires_service_identity():
    """System env-var update with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_env_vars.env_var_service.update_system_env_var",
            return_value=_system_env_var_response(),
        ) as update_system_env_var:
            response = client.patch(
                "/internal/system-env-vars/1",
                json={"value": "updated"},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    update_system_env_var.assert_not_called()


def test_internal_system_env_var_update_accepts_valid_token_and_service():
    """System env-var update accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_env_vars.env_var_service.update_system_env_var",
            return_value=_system_env_var_response(),
        ) as update_system_env_var:
            response = client.patch(
                "/internal/system-env-vars/1",
                json={"value": "updated"},
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    update_system_env_var.assert_called_once()
    assert update_system_env_var.call_args.args[:2] == (db, 1)


def test_internal_system_env_var_delete_requires_service_identity():
    """System env-var deletion with valid token but missing service header fails."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_env_vars.env_var_service.delete_system_env_var"
        ) as delete_system_env_var:
            response = client.delete(
                "/internal/system-env-vars/1",
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 403
    assert "Service identity required" in response.json()["message"]
    delete_system_env_var.assert_not_called()


def test_internal_system_env_var_delete_accepts_valid_token_and_service():
    """System env-var deletion accepts executor_manager service identity."""
    client = _client()
    db = MagicMock()
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch(
            "app.api.v1.internal_env_vars.env_var_service.delete_system_env_var"
        ) as delete_system_env_var:
            response = client.delete(
                "/internal/system-env-vars/1",
                headers={
                    "X-Internal-Token": "internal-token",
                    "X-Internal-Service": "executor_manager",
                },
            )

    assert response.status_code == 200
    delete_system_env_var.assert_called_once_with(db, 1)


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
