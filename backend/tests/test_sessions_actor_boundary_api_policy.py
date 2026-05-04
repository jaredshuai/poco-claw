"""Tests for sessions API Actor boundary migration.

These tests verify that the six migrated public endpoints use Actor.user_id
rather than a direct user_id parameter, and preserve request passthrough behavior.
"""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.identity import Actor
from app.api.v1.sessions import (
    create_session,
    list_sessions,
    cancel_session,
    branch_session,
    regenerate_message,
    edit_message_and_regenerate,
)


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_session_service() -> MagicMock:
    service = MagicMock()
    service.create_session = MagicMock()
    service.list_sessions = MagicMock()
    service.cancel_session = MagicMock()
    service.branch_session = MagicMock()
    service.regenerate_from_message = MagicMock()
    service.edit_message_and_regenerate = MagicMock()
    return service


class TestCreateSessionActorBoundary:
    """Tests for create_session Actor boundary."""

    def test_uses_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-123")
        mock_session = MagicMock()
        mock_session_service.create_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.model_dump = MagicMock(return_value={})

        with patch(
            "app.api.v1.sessions.SessionResponse.model_validate"
        ) as mock_validate:
            mock_validate.return_value = MagicMock()
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(create_session(request=request, actor=actor, db=mock_db))

        mock_session_service.create_session.assert_called_once_with(
            mock_db, "user-123", request
        )

    def test_preserves_success_message(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-123")
        mock_session = MagicMock()
        mock_session_service.create_session.return_value = mock_session

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(create_session(request=request, actor=actor, db=mock_db))

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args
        assert call_kwargs[1]["message"] == "Session created successfully"


class TestListSessionsActorBoundary:
    """Tests for list_sessions Actor boundary."""

    def test_uses_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-456")
        mock_session_service.list_sessions.return_value = []

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(
                    list_sessions(
                        actor=actor,
                        limit=50,
                        offset=10,
                        project_id=None,
                        kind="chat",
                        db=mock_db,
                    )
                )

        mock_session_service.list_sessions.assert_called_once_with(
            mock_db, "user-456", 50, 10, None, kind="chat"
        )

    def test_preserves_kind_normalization_empty_to_none(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-456")
        mock_session_service.list_sessions.return_value = []

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    list_sessions(
                        actor=actor,
                        limit=100,
                        offset=0,
                        project_id=None,
                        kind="  ",
                        db=mock_db,
                    )
                )

        call_args = mock_session_service.list_sessions.call_args
        assert call_args[1]["kind"] is None  # kind kwarg should be None

    def test_preserves_kind_normalization_all_to_none(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-456")
        mock_session_service.list_sessions.return_value = []

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    list_sessions(
                        actor=actor,
                        limit=100,
                        offset=0,
                        project_id=None,
                        kind="ALL",
                        db=mock_db,
                    )
                )

        call_args = mock_session_service.list_sessions.call_args
        assert call_args[1]["kind"] is None

    def test_preserves_project_id_and_pagination(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-456")
        mock_session_service.list_sessions.return_value = []
        project_id = uuid.uuid4()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    list_sessions(
                        actor=actor,
                        limit=25,
                        offset=50,
                        project_id=project_id,
                        kind="code",
                        db=mock_db,
                    )
                )

        mock_session_service.list_sessions.assert_called_once_with(
            mock_db, "user-456", 25, 50, project_id, kind="code"
        )

    def test_preserves_success_message(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-456")
        mock_session_service.list_sessions.return_value = []

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        with patch("app.api.v1.sessions.SessionResponse.model_validate"):
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(
                    list_sessions(
                        actor=actor,
                        limit=100,
                        offset=0,
                        project_id=None,
                        kind="chat",
                        db=mock_db,
                    )
                )

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args
        assert call_kwargs[1]["message"] == "Sessions retrieved successfully"


class TestCancelSessionActorBoundary:
    """Tests for cancel_session Actor boundary."""

    def test_uses_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-789")
        session_id = uuid.uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.status = "canceled"

        mock_session_service.cancel_session.return_value = (
            mock_session,
            2,
            3,
            1,
        )

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.reason = "user requested"

        with patch("app.api.v1.sessions._cancel_executor_manager", return_value=True):
            with patch("app.api.v1.sessions.SessionCancelResponse") as mock_response:
                mock_response.return_value = MagicMock()
                with patch("app.api.v1.sessions.Response.success") as mock_success:
                    mock_success.return_value = MagicMock()
                    _run(
                        cancel_session(
                            session_id=session_id,
                            request=request,
                            actor=actor,
                            db=mock_db,
                        )
                    )

        mock_session_service.cancel_session.assert_called_once_with(
            mock_db, session_id, user_id="user-789", reason="user requested"
        )

    def test_preserves_executor_manager_cancel_call(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-789")
        session_id = uuid.uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.status = "canceled"

        mock_session_service.cancel_session.return_value = (
            mock_session,
            0,
            0,
            0,
        )

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.reason = "timeout"

        with patch("app.api.v1.sessions._cancel_executor_manager") as mock_cancel:
            mock_cancel.return_value = True
            with patch("app.api.v1.sessions.SessionCancelResponse"):
                with patch("app.api.v1.sessions.Response.success"):
                    _run(
                        cancel_session(
                            session_id=session_id,
                            request=request,
                            actor=actor,
                            db=mock_db,
                        )
                    )

        mock_cancel.assert_called_once_with(session_id, "timeout")

    def test_preserves_response_data_construction(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-789")
        session_id = uuid.uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.status = "canceled"

        mock_session_service.cancel_session.return_value = (
            mock_session,
            5,
            2,
            1,
        )

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.reason = None

        with patch("app.api.v1.sessions._cancel_executor_manager", return_value=False):
            with patch("app.api.v1.sessions.SessionCancelResponse") as mock_response:
                mock_response.return_value = MagicMock()
                with patch("app.api.v1.sessions.Response.success") as mock_success:
                    mock_success.return_value = MagicMock()
                    _run(
                        cancel_session(
                            session_id=session_id,
                            request=request,
                            actor=actor,
                            db=mock_db,
                        )
                    )

        mock_response.assert_called_once_with(
            session_id=session_id,
            status="canceled",
            canceled_runs=5,
            canceled_queued_queries=2,
            expired_user_input_requests=1,
            executor_cancelled=False,
        )

    def test_preserves_success_message(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-789")
        session_id = uuid.uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.status = "canceled"

        mock_session_service.cancel_session.return_value = (mock_session, 0, 0, 0)

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.reason = None

        with patch("app.api.v1.sessions._cancel_executor_manager", return_value=True):
            with patch("app.api.v1.sessions.SessionCancelResponse"):
                with patch("app.api.v1.sessions.Response.success") as mock_success:
                    mock_success.return_value = MagicMock()
                    _run(
                        cancel_session(
                            session_id=session_id,
                            request=request,
                            actor=actor,
                            db=mock_db,
                        )
                    )

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args
        assert call_kwargs[1]["message"] == "Session canceled successfully"


class TestBranchSessionActorBoundary:
    """Tests for branch_session Actor boundary."""

    def test_uses_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-branch")
        session_id = uuid.uuid4()
        message_id = 42
        mock_branched = MagicMock()
        mock_branched.id = uuid.uuid4()

        mock_session_service.branch_session.return_value = mock_branched

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.message_id = message_id

        with patch("app.api.v1.sessions.SessionBranchResponse") as mock_response:
            mock_response.return_value = MagicMock()
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    branch_session(
                        session_id=session_id,
                        request=request,
                        actor=actor,
                        db=mock_db,
                    )
                )

        mock_session_service.branch_session.assert_called_once_with(
            mock_db, session_id, user_id="user-branch", cutoff_message_id=message_id
        )

    def test_preserves_cutoff_message_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-branch")
        session_id = uuid.uuid4()
        message_id = 123
        mock_branched = MagicMock()
        mock_branched.id = uuid.uuid4()

        mock_session_service.branch_session.return_value = mock_branched

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.message_id = message_id

        with patch("app.api.v1.sessions.SessionBranchResponse") as mock_response:
            mock_response.return_value = MagicMock()
            with patch("app.api.v1.sessions.Response.success"):
                _run(
                    branch_session(
                        session_id=session_id,
                        request=request,
                        actor=actor,
                        db=mock_db,
                    )
                )

        call_kwargs = mock_session_service.branch_session.call_args
        assert call_kwargs[1]["cutoff_message_id"] == message_id

    def test_preserves_success_message(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-branch")
        session_id = uuid.uuid4()
        mock_branched = MagicMock()
        mock_branched.id = uuid.uuid4()

        mock_session_service.branch_session.return_value = mock_branched

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.message_id = 1

        with patch("app.api.v1.sessions.SessionBranchResponse"):
            with patch("app.api.v1.sessions.Response.success") as mock_success:
                mock_success.return_value = MagicMock()
                _run(
                    branch_session(
                        session_id=session_id,
                        request=request,
                        actor=actor,
                        db=mock_db,
                    )
                )

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args
        assert call_kwargs[1]["message"] == "Session branched successfully"


class TestRegenerateMessageActorBoundary:
    """Tests for regenerate_message Actor boundary."""

    def test_uses_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-regen")
        session_id = uuid.uuid4()
        mock_result = MagicMock()

        mock_session_service.regenerate_from_message.return_value = mock_result

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 10
        request.assistant_message_id = 11
        request.model = "claude-3"
        request.model_provider_id = None

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                regenerate_message(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_session_service.regenerate_from_message.assert_called_once_with(
            mock_db,
            session_id,
            user_id="user-regen",
            user_message_id=10,
            assistant_message_id=11,
            model="claude-3",
            model_provider_id=None,
        )

    def test_preserves_message_ids(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-regen")
        session_id = uuid.uuid4()

        mock_session_service.regenerate_from_message.return_value = MagicMock()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 50
        request.assistant_message_id = 51
        request.model = None
        request.model_provider_id = None

        with patch("app.api.v1.sessions.Response.success"):
            _run(
                regenerate_message(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_session_service.regenerate_from_message.call_args
        assert call_args[1]["user_message_id"] == 50
        assert call_args[1]["assistant_message_id"] == 51

    def test_preserves_model_and_provider(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-regen")
        session_id = uuid.uuid4()
        provider_id = uuid.uuid4()

        mock_session_service.regenerate_from_message.return_value = MagicMock()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 1
        request.assistant_message_id = 2
        request.model = "claude-sonnet"
        request.model_provider_id = provider_id

        with patch("app.api.v1.sessions.Response.success"):
            _run(
                regenerate_message(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_session_service.regenerate_from_message.call_args
        assert call_args[1]["model"] == "claude-sonnet"
        assert call_args[1]["model_provider_id"] == provider_id

    def test_preserves_success_message(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-regen")
        session_id = uuid.uuid4()

        mock_session_service.regenerate_from_message.return_value = MagicMock()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 1
        request.assistant_message_id = 2
        request.model = None
        request.model_provider_id = None

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                regenerate_message(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args
        assert call_kwargs[1]["message"] == "Message regenerated successfully"


class TestEditMessageAndRegenerateActorBoundary:
    """Tests for edit_message_and_regenerate Actor boundary."""

    def test_uses_actor_user_id(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-edit")
        session_id = uuid.uuid4()
        mock_result = MagicMock()

        mock_session_service.edit_message_and_regenerate.return_value = mock_result

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 20
        request.content = "edited content"
        request.model = None
        request.model_provider_id = None

        with patch("app.api.v1.sessions.Response.success"):
            _run(
                edit_message_and_regenerate(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_session_service.edit_message_and_regenerate.assert_called_once_with(
            mock_db,
            session_id,
            user_id="user-edit",
            user_message_id=20,
            content="edited content",
            model=None,
            model_provider_id=None,
        )

    def test_preserves_message_id_and_content(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-edit")
        session_id = uuid.uuid4()

        mock_session_service.edit_message_and_regenerate.return_value = MagicMock()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 99
        request.content = "new message text"
        request.model = None
        request.model_provider_id = None

        with patch("app.api.v1.sessions.Response.success"):
            _run(
                edit_message_and_regenerate(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_session_service.edit_message_and_regenerate.call_args
        assert call_args[1]["user_message_id"] == 99
        assert call_args[1]["content"] == "new message text"

    def test_preserves_model_and_provider(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-edit")
        session_id = uuid.uuid4()
        provider_id = uuid.uuid4()

        mock_session_service.edit_message_and_regenerate.return_value = MagicMock()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 1
        request.content = "test"
        request.model = "claude-opus"
        request.model_provider_id = provider_id

        with patch("app.api.v1.sessions.Response.success"):
            _run(
                edit_message_and_regenerate(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_session_service.edit_message_and_regenerate.call_args
        assert call_args[1]["model"] == "claude-opus"
        assert call_args[1]["model_provider_id"] == provider_id

    def test_preserves_success_message(
        self, mock_db, mock_session_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-edit")
        session_id = uuid.uuid4()

        mock_session_service.edit_message_and_regenerate.return_value = MagicMock()

        monkeypatch.setattr("app.api.v1.sessions.session_service", mock_session_service)

        request = MagicMock()
        request.user_message_id = 1
        request.content = "test"
        request.model = None
        request.model_provider_id = None

        with patch("app.api.v1.sessions.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                edit_message_and_regenerate(
                    session_id=session_id,
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args
        assert call_kwargs[1]["message"] == "Message edited and regenerated"
