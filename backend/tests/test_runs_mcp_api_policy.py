"""Tests for runs_mcp API policy engine integration."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyDecision
from app.api.v1.runs_mcp import (
    _ensure_run_belongs_to_user,
    list_lifecycle_events,
    list_mcp_connections,
    list_mcp_connection_events,
    list_permission_audit,
)


class FakePolicyEngine:
    """Fake policy engine for testing."""

    def __init__(self, allow: bool = True):
        self._allow = allow
        self.last_actor = None
        self.last_owner_user_id = None

    def can_access_user_resource(
        self, actor: Actor, owner_user_id: str
    ) -> PolicyDecision:
        self.last_actor = actor
        self.last_owner_user_id = owner_user_id
        if self._allow:
            return PolicyDecision(allowed=True)
        return PolicyDecision(allowed=False, reason="user_owner_mismatch")


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_session_service() -> MagicMock:
    service = MagicMock()
    service.get_session = MagicMock()
    return service


@pytest.fixture
def mock_run_service() -> MagicMock:
    service = MagicMock()
    service.get_run = MagicMock()
    return service


@pytest.fixture
def mock_mcp_connection_service() -> MagicMock:
    service = MagicMock()
    service.list_run_connections = MagicMock(return_value=[])
    return service


class TestOwnershipHelper:
    """Tests for _ensure_run_belongs_to_user helper."""

    def test_passes_actor_and_owner_to_policy_engine_on_success(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        _ensure_run_belongs_to_user(mock_db, run_id, actor, fake_policy)

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id

    def test_raises_forbidden_with_exact_message_when_policy_denies(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _ensure_run_belongs_to_user(mock_db, run_id, actor, fake_policy)

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"


class TestListMcpConnectionsPolicy:
    """Tests for list_mcp_connections endpoint policy integration."""

    def test_calls_helper_with_actor_and_policy_engine(
        self,
        mock_db,
        mock_session_service,
        mock_run_service,
        mock_mcp_connection_service,
        monkeypatch,
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)
        monkeypatch.setattr(
            "app.api.v1.runs_mcp.McpConnectionService",
            lambda: mock_mcp_connection_service,
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        list_mcp_connections(
            run_id=run_id,
            actor=actor,
            policy_engine=fake_policy,
            db=mock_db,
        )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_mcp_connection_service.list_run_connections.assert_called_once_with(
            mock_db, run_id
        )

    def test_denied_access_prevents_connection_list(
        self,
        mock_db,
        mock_session_service,
        mock_run_service,
        mock_mcp_connection_service,
        monkeypatch,
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)
        monkeypatch.setattr(
            "app.api.v1.runs_mcp.McpConnectionService",
            lambda: mock_mcp_connection_service,
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            list_mcp_connections(
                run_id=run_id,
                actor=actor,
                policy_engine=fake_policy,
                db=mock_db,
            )

        mock_mcp_connection_service.list_run_connections.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"


class TestListMcpConnectionEventsPolicy:
    """Tests for list_mcp_connection_events endpoint policy integration."""

    def test_calls_helper_before_reading_events(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        list_mcp_connection_events(
            run_id=run_id,
            actor=actor,
            policy_engine=fake_policy,
            db=mock_db,
        )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id

    def test_denied_access_prevents_event_query(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            list_mcp_connection_events(
                run_id=run_id,
                actor=actor,
                policy_engine=fake_policy,
                db=mock_db,
            )

        mock_db.query.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"


class TestListPermissionAuditPolicy:
    """Tests for list_permission_audit endpoint policy integration."""

    def test_calls_helper_before_reading_audit_events(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        list_permission_audit(
            run_id=run_id,
            actor=actor,
            policy_engine=fake_policy,
            db=mock_db,
        )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id

    def test_denied_access_prevents_audit_query(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            list_permission_audit(
                run_id=run_id,
                actor=actor,
                policy_engine=fake_policy,
                db=mock_db,
            )

        mock_db.query.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"


class TestListLifecycleEventsPolicy:
    """Tests for list_lifecycle_events endpoint policy integration."""

    def test_calls_helper_before_reading_lifecycle_events(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        (
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value
        ) = []

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        list_lifecycle_events(
            run_id=run_id,
            actor=actor,
            policy_engine=fake_policy,
            db=mock_db,
        )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id

    def test_denied_access_prevents_lifecycle_event_query(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        run_id = uuid.uuid4()
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_run = MagicMock()
        mock_run.session_id = session_id
        mock_run_service.get_run.return_value = mock_run

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs_mcp.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs_mcp.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            list_lifecycle_events(
                run_id=run_id,
                actor=actor,
                policy_engine=fake_policy,
                db=mock_db,
            )

        mock_db.query.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"
