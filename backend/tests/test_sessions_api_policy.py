"""Tests for sessions API policy engine integration."""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyDecision
from app.api.v1.sessions import (
    _ensure_session_owner,
    get_session,
    get_session_state,
    update_session,
    delete_session,
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
    service.update_session = MagicMock()
    service.delete_session = MagicMock()
    return service


class TestEnsureSessionOwner:
    """Tests for _ensure_session_owner helper."""

    def test_passes_actor_and_owner_user_id_to_policy_engine(self) -> None:
        actor = Actor(user_id="user-123")
        fake_policy = FakePolicyEngine(allow=True)

        _ensure_session_owner(actor, fake_policy, "owner-456")

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == "owner-456"

    def test_raises_forbidden_with_exact_message_when_denied(self) -> None:
        actor = Actor(user_id="user-123")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _ensure_session_owner(actor, fake_policy, "owner-456")

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"


class TestGetSessionPolicy:
    """Tests for get_session endpoint policy integration."""

    def test_allowed_path_calls_session_service_and_policy_engine(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(
                    get_session(
                        session_id=session_id,
                        actor=actor,
                        policy_engine=fake_policy,
                        db=mock_db,
                    )
                )

        mock_session_service.get_session.assert_called_once_with(mock_db, session_id)
        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id

    def test_denied_path_raises_forbidden(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"


class TestGetSessionStatePolicy:
    """Tests for get_session_state endpoint policy integration."""

    def test_uses_policy_engine_for_authorization(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.SessionStateResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    get_session_state(
                        session_id=session_id,
                        actor=actor,
                        policy_engine=fake_policy,
                        db=mock_db,
                    )
                )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id


class TestUpdateSessionPolicy:
    """Tests for update_session endpoint policy integration."""

    def test_denied_path_raises_forbidden_and_does_not_call_update(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        mock_request = MagicMock()

        with pytest.raises(AppException) as exc_info:
            _run(
                update_session(
                    session_id=session_id,
                    request=mock_request,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        mock_session_service.update_session.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"

    def test_allowed_path_calls_update_session(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session
        mock_session_service.update_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        mock_request = MagicMock()

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    update_session(
                        session_id=session_id,
                        request=mock_request,
                        actor=actor,
                        policy_engine=fake_policy,
                        db=mock_db,
                    )
                )

        mock_session_service.update_session.assert_called_once_with(
            mock_db, session_id, mock_request
        )


class TestDeleteSessionPolicy:
    """Tests for delete_session endpoint policy integration."""

    def test_denied_path_raises_forbidden_and_does_not_call_delete(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                delete_session(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        mock_session_service.delete_session.assert_not_called()
        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"

    def test_allowed_path_calls_delete_session(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success"):
            _run(
                delete_session(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        mock_session_service.delete_session.assert_called_once_with(mock_db, session_id)
