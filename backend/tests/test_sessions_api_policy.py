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
    get_session_messages,
    get_session_messages_delta,
    get_session_messages_with_files,
    get_session_messages_with_files_delta,
    get_session_message_attachments,
    get_session_message_attachments_delta,
    get_session_tool_executions,
    get_session_tool_executions_delta,
    get_session_browser_screenshot,
    get_session_usage,
    get_session_workspace_files,
    get_session_workspace_archive,
    get_session_workspace_folder_archive,
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


class TestGetSessionMessagesPolicy:
    """Tests for get_session_messages endpoint policy integration."""

    def test_allowed_path_uses_policy_and_calls_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        mock_message_service.get_message_responses.return_value = []
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_messages(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_message_service.get_message_responses.assert_called_once_with(
            mock_db, session_id, user_id=actor.user_id
        )

    def test_denied_path_raises_forbidden_and_does_not_call_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_messages(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_message_service.get_message_responses.assert_not_called()


class TestGetSessionMessagesDeltaPolicy:
    """Tests for get_session_messages_delta endpoint policy integration."""

    def test_allowed_path_passes_actor_user_id_and_params_to_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        mock_message_service.get_messages_delta.return_value = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_messages_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_message_id=42,
                    limit=100,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_message_service.get_messages_delta.assert_called_once_with(
            mock_db,
            session_id,
            user_id=actor.user_id,
            after_message_id=42,
            limit=100,
        )


class TestGetSessionMessageAttachmentsPolicy:
    """Tests for get_session_message_attachments endpoint policy integration."""

    def test_allowed_path_calls_message_service_with_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        mock_message_service.get_message_attachments.return_value = []
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_message_attachments(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_message_service.get_message_attachments.assert_called_once_with(
            mock_db, session_id, user_id=actor.user_id
        )

    def test_denied_path_raises_forbidden_and_does_not_call_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_message_attachments(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_message_service.get_message_attachments.assert_not_called()


class TestGetSessionMessagesWithFilesPolicy:
    """Tests for get_session_messages_with_files endpoint policy integration."""

    def test_allowed_path_calls_message_service_with_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        mock_message_service.get_messages_with_files.return_value = []
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_messages_with_files(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_message_service.get_messages_with_files.assert_called_once_with(
            mock_db, session_id, user_id=actor.user_id
        )

    def test_denied_path_raises_forbidden_and_does_not_call_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_messages_with_files(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_message_service.get_messages_with_files.assert_not_called()


class TestGetSessionMessagesWithFilesDeltaPolicy:
    """Tests for get_session_messages_with_files_delta endpoint policy integration."""

    def test_allowed_path_passes_actor_user_id_and_params_to_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        mock_message_service.get_messages_with_files_delta.return_value = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_messages_with_files_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_message_id=10,
                    limit=50,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_message_service.get_messages_with_files_delta.assert_called_once_with(
            mock_db,
            session_id,
            user_id=actor.user_id,
            after_message_id=10,
            limit=50,
        )

    def test_denied_path_raises_forbidden_and_does_not_call_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_messages_with_files_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_message_id=0,
                    limit=200,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_message_service.get_messages_with_files_delta.assert_not_called()


class TestGetSessionMessageAttachmentsDeltaPolicy:
    """Tests for get_session_message_attachments_delta endpoint policy integration."""

    def test_allowed_path_passes_actor_user_id_and_params_to_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        mock_message_service.get_message_attachments_delta.return_value = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_message_attachments_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_message_id=5,
                    limit=100,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_message_service.get_message_attachments_delta.assert_called_once_with(
            mock_db,
            session_id,
            user_id=actor.user_id,
            after_message_id=5,
            limit=100,
        )

    def test_denied_path_raises_forbidden_and_does_not_call_message_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_message_service = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.message_service", mock_message_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_message_attachments_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_message_id=0,
                    limit=200,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_message_service.get_message_attachments_delta.assert_not_called()


class TestGetSessionToolExecutionsPolicy:
    """Tests for get_session_tool_executions endpoint policy integration."""

    def test_allowed_path_uses_policy_and_calls_tool_execution_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_tool_execution_service = MagicMock()
        mock_tool_execution_service.get_tool_executions.return_value = []
        monkeypatch.setattr(
            "app.api.v1.sessions.tool_execution_service", mock_tool_execution_service
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_tool_executions(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    limit=500,
                    offset=0,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_tool_execution_service.get_tool_executions.assert_called_once_with(
            mock_db, session_id, limit=500, offset=0
        )

    def test_denied_path_raises_forbidden_and_does_not_call_tool_execution_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_tool_execution_service = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.tool_execution_service", mock_tool_execution_service
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_tool_executions(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    limit=500,
                    offset=0,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_tool_execution_service.get_tool_executions.assert_not_called()


class TestGetSessionToolExecutionsDeltaPolicy:
    """Tests for get_session_tool_executions_delta endpoint policy integration."""

    def test_allowed_path_passes_params_to_tool_execution_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        from datetime import datetime, timezone

        session_id = uuid.uuid4()
        owner_user_id = "owner-123"
        after_created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        after_id = uuid.uuid4()

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_tool_execution_service = MagicMock()
        mock_tool_execution_service.get_tool_executions_delta.return_value = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.tool_execution_service", mock_tool_execution_service
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_tool_executions_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_created_at=after_created_at,
                    after_id=after_id,
                    limit=100,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_tool_execution_service.get_tool_executions_delta.assert_called_once_with(
            mock_db,
            session_id,
            after_created_at=after_created_at,
            after_id=after_id,
            limit=100,
        )

    def test_denied_path_raises_forbidden_and_does_not_call_tool_execution_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_tool_execution_service = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.tool_execution_service", mock_tool_execution_service
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_tool_executions_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_created_at=None,
                    after_id=None,
                    limit=200,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_tool_execution_service.get_tool_executions_delta.assert_not_called()

    def test_after_id_without_after_created_at_raises_bad_request_after_auth(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        """Authorization succeeds but BAD_REQUEST raised for invalid cursor params."""
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_tool_execution_service = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.tool_execution_service", mock_tool_execution_service
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_tool_executions_delta(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    after_created_at=None,
                    after_id=uuid.uuid4(),
                    limit=200,
                    db=mock_db,
                )
            )

        # Authorization succeeded (policy engine was called)
        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        # But BAD_REQUEST raised for cursor validation
        assert exc_info.value.error_code == ErrorCode.BAD_REQUEST
        assert "after_created_at is required" in str(exc_info.value.message)
        mock_tool_execution_service.get_tool_executions_delta.assert_not_called()


class TestGetSessionUsagePolicy:
    """Tests for get_session_usage endpoint policy integration."""

    def test_allowed_path_uses_policy_and_calls_usage_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_usage_service = MagicMock()
        mock_usage_service.get_usage_summary.return_value = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.usage_service", mock_usage_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_usage(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_usage_service.get_usage_summary.assert_called_once_with(
            mock_db, session_id
        )

    def test_denied_path_raises_forbidden_and_does_not_call_usage_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_usage_service = MagicMock()
        monkeypatch.setattr("app.api.v1.sessions.usage_service", mock_usage_service)

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_usage(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_usage_service.get_usage_summary.assert_not_called()


class TestGetSessionBrowserScreenshotPolicy:
    """Tests for get_session_browser_screenshot endpoint policy integration."""

    def test_allowed_path_uses_policy_and_builds_screenshot_key(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"
        tool_use_id = "tool-use-456"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.presign_get.return_value = "https://storage.url/screenshot.png"
        monkeypatch.setattr(
            "app.api.v1.sessions.get_storage_service", lambda: mock_storage
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.build_browser_screenshot_key") as mock_key:
            mock_key.return_value = "screenshots/owner-123/session-id/tool-use-456"
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(
                    get_session_browser_screenshot(
                        session_id=session_id,
                        tool_use_id=tool_use_id,
                        actor=actor,
                        policy_engine=fake_policy,
                        db=mock_db,
                    )
                )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_key.assert_called_once_with(
            user_id=actor.user_id,
            session_id=str(session_id),
            tool_use_id=tool_use_id,
        )
        mock_storage.exists.assert_called_once()
        mock_storage.presign_get.assert_called_once()

    def test_denied_path_raises_forbidden_and_does_not_build_key(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"
        tool_use_id = "tool-use-456"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_storage = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.get_storage_service", lambda: mock_storage
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with patch("app.api.v1.sessions.build_browser_screenshot_key") as mock_key:
            with pytest.raises(AppException) as exc_info:
                _run(
                    get_session_browser_screenshot(
                        session_id=session_id,
                        tool_use_id=tool_use_id,
                        actor=actor,
                        policy_engine=fake_policy,
                        db=mock_db,
                    )
                )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_key.assert_not_called()
        mock_storage.exists.assert_not_called()
        mock_storage.presign_get.assert_not_called()

    def test_not_ready_path_raises_404_after_successful_auth(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"
        tool_use_id = "tool-use-456"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_storage = MagicMock()
        mock_storage.exists.return_value = False
        monkeypatch.setattr(
            "app.api.v1.sessions.get_storage_service", lambda: mock_storage
        )

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        from fastapi import HTTPException

        with patch("app.api.v1.sessions.build_browser_screenshot_key") as mock_key:
            mock_key.return_value = "screenshots/owner-123/session-id/tool-use-456"
            with pytest.raises(HTTPException) as exc_info:
                _run(
                    get_session_browser_screenshot(
                        session_id=session_id,
                        tool_use_id=tool_use_id,
                        actor=actor,
                        policy_engine=fake_policy,
                        db=mock_db,
                    )
                )

        # Authorization succeeded
        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        # But storage.exists returned False -> 404
        assert exc_info.value.status_code == 404
        assert "not ready" in exc_info.value.detail.lower()
        mock_storage.presign_get.assert_not_called()


class TestGetSessionWorkspaceFilesPolicy:
    """Tests for get_session_workspace_files endpoint policy integration."""

    def test_allowed_path_with_no_manifest_returns_empty_after_auth(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        """When workspace_manifest_key is None, returns empty data after auth."""
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session.workspace_manifest_key = None
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_workspace_files(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_success.assert_called_once()
        call_args = mock_success.call_args
        assert call_args[1]["data"] == []
        assert call_args[1]["message"] == "Workspace export not ready"

    def test_denied_path_raises_forbidden_and_does_not_touch_storage(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_storage = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.get_storage_service", lambda: mock_storage
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_workspace_files(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_storage.get_manifest.assert_not_called()


class TestGetSessionWorkspaceArchivePolicy:
    """Tests for get_session_workspace_archive endpoint policy integration."""

    def test_allowed_path_with_no_archive_key_returns_none_url_after_auth(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        """When archive key is missing or export not ready, returns url=None."""
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session.workspace_archive_key = ""
        mock_session.workspace_export_status = "pending"
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_workspace_archive(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_success.assert_called_once()
        call_args = mock_success.call_args
        assert call_args[1]["data"].url is None

    def test_denied_path_raises_forbidden_and_does_not_touch_storage(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_storage = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.get_storage_service", lambda: mock_storage
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_workspace_archive(
                    session_id=session_id,
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_storage.presign_get.assert_not_called()


class TestGetSessionWorkspaceFolderArchivePolicy:
    """Tests for get_session_workspace_folder_archive endpoint policy integration."""

    def test_allowed_path_with_export_not_ready_returns_none_url_after_auth(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        """When export status is not ready, returns url=None after auth."""
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session.workspace_export_status = "pending"
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        actor = Actor(user_id=owner_user_id)
        fake_policy = FakePolicyEngine(allow=True)

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                get_session_workspace_folder_archive(
                    session_id=session_id,
                    path="some/folder",
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert fake_policy.last_actor is actor
        assert fake_policy.last_owner_user_id == owner_user_id
        mock_success.assert_called_once()
        call_args = mock_success.call_args
        assert call_args[1]["data"].url is None

    def test_denied_path_raises_forbidden_and_does_not_call_archive_service(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        session_id = uuid.uuid4()
        owner_user_id = "owner-123"

        mock_session = MagicMock()
        mock_session.user_id = owner_user_id
        mock_session_service.get_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        mock_archive_service = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.sessions.workspace_archive_service", mock_archive_service
        )

        actor = Actor(user_id="different-user")
        fake_policy = FakePolicyEngine(allow=False)

        with pytest.raises(AppException) as exc_info:
            _run(
                get_session_workspace_folder_archive(
                    session_id=session_id,
                    path="some/folder",
                    actor=actor,
                    policy_engine=fake_policy,
                    db=mock_db,
                )
            )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert str(exc_info.value.message) == "Session does not belong to the user"
        mock_archive_service.get_folder_archive.assert_not_called()
