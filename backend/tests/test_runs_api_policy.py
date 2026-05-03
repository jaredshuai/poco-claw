"""Tests for runs API policy engine integration."""

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyDecision
from app.api.v1.runs import (
    get_run,
    list_runs_by_session,
    list_run_mcp_connections,
)


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


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
    service.list_runs = MagicMock(return_value=[])
    return service


@pytest.fixture
def mock_mcp_connection_service() -> MagicMock:
    service = MagicMock()
    service.list_run_connections = MagicMock(return_value=[])
    return service


class TestGetRunPolicy:
    """Tests for get_run endpoint policy integration."""

    def test_passes_actor_to_policy_engine_on_success(
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

        monkeypatch.setattr("app.api.v1.runs.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        _run(
            get_run(
                run_id=run_id,
                actor=actor,
                policy_engine=fake_policy,
                db=mock_db,
            )
        )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id

    def test_raises_forbidden_when_policy_denies(
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

        monkeypatch.setattr("app.api.v1.runs.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_run(
                    run_id=run_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"


class TestListRunsBySessionPolicy:
    """Tests for list_runs_by_session endpoint policy integration."""

    def test_denies_before_calling_list_runs(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                list_runs_by_session(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    limit=100,
                    offset=0,
                    db=mock_db,
                )
            )

        mock_run_service.list_runs.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"

    def test_allows_matching_user(
        self, mock_db, mock_session_service, mock_run_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.runs.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        _run(
            list_runs_by_session(
                session_id=session_id,
                actor=actor,
                policy_engine=fake_policy,
                limit=100,
                offset=0,
                db=mock_db,
            )
        )

        mock_run_service.list_runs.assert_called_once()
        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id


class TestListRunMcpConnectionsPolicy:
    """Tests for list_run_mcp_connections endpoint policy integration."""

    def test_uses_policy_before_returning_connections(
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

        monkeypatch.setattr("app.api.v1.runs.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs.session_service", mock_session_service)
        monkeypatch.setattr(
            "app.api.v1.runs.mcp_connection_service", mock_mcp_connection_service
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        _run(
            list_run_mcp_connections(
                run_id=run_id,
                actor=actor,
                policy_engine=fake_policy,
                db=mock_db,
            )
        )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_mcp_connection_service.list_run_connections.assert_called_once_with(
            mock_db, run_id
        )

    def test_denies_access_to_non_owner(
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

        monkeypatch.setattr("app.api.v1.runs.run_service", mock_run_service)
        monkeypatch.setattr("app.api.v1.runs.session_service", mock_session_service)
        monkeypatch.setattr(
            "app.api.v1.runs.mcp_connection_service", mock_mcp_connection_service
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                list_run_mcp_connections(
                    run_id=run_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        mock_mcp_connection_service.list_run_connections.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Run does not belong to the user"
