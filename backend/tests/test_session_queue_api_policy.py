"""Tests for session_queue API policy engine integration."""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyDecision
from app.api.v1 import session_queue


def _run(coro):
    """Helper to run async functions in tests."""
    return asyncio.run(coro)


class TestGetOwnedSession:
    """Tests for the _get_owned_session helper."""

    def test_passes_actor_and_owner_user_id_to_policy_engine_when_allowed(self):
        """Helper passes Actor and owner_user_id to policy engine when allowed."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        db_session = MagicMock()
        db_session.user_id = "user-123"
        db_session.id = uuid.uuid4()

        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            result = session_queue._get_owned_session(
                mock_db, uuid.uuid4(), actor, policy_engine
            )

        policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "user-123"
        )
        assert result is db_session

    def test_raises_app_exception_when_policy_denies(self):
        """Helper raises AppException with FORBIDDEN code when policy denies."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        db_session = MagicMock()
        db_session.user_id = "other-user"

        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with pytest.raises(AppException) as exc_info:
                session_queue._get_owned_session(
                    mock_db, uuid.uuid4(), actor, policy_engine
                )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert exc_info.value.message == "Session does not belong to the user"


class TestListQueuedQueries:
    """Tests for list_queued_queries endpoint."""

    def test_passes_actor_and_policy_engine_through_helper(self):
        """Endpoint passes Actor and PolicyEngine through ownership helper."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        session_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.id = session_id
        db_session.user_id = "user-123"

        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service,
                "list_item_responses",
                return_value=[],
            ) as mock_list:
                _run(
                    session_queue.list_queued_queries(
                        session_id=session_id,
                        actor=actor,
                        policy_engine=policy_engine,
                        db=mock_db,
                    )
                )

        policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "user-123"
        )
        mock_list.assert_called_once()

    def test_denied_access_prevents_service_call(self):
        """Denied access prevents session_queue_service method calls."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        session_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.user_id = "other-user"

        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service, "list_item_responses"
            ) as mock_list:
                with pytest.raises(AppException):
                    _run(
                        session_queue.list_queued_queries(
                            session_id=session_id,
                            actor=actor,
                            policy_engine=policy_engine,
                            db=mock_db,
                        )
                    )

        mock_list.assert_not_called()


class TestUpdateQueuedQuery:
    """Tests for update_queued_query endpoint."""

    def test_passes_actor_and_policy_engine_through_helper(self):
        """Endpoint passes Actor and PolicyEngine through ownership helper."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        session_id = uuid.uuid4()
        item_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.id = session_id
        db_session.user_id = "user-123"

        mock_item = MagicMock()
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_response = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service,
                "update_item",
                return_value=mock_item,
            ) as mock_update:
                with patch.object(
                    session_queue.SessionQueueItemResponse,
                    "model_validate",
                    return_value=mock_response,
                ):
                    _run(
                        session_queue.update_queued_query(
                            session_id=session_id,
                            item_id=item_id,
                            request=mock_request,
                            actor=actor,
                            policy_engine=policy_engine,
                            db=mock_db,
                        )
                    )

        policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "user-123"
        )
        mock_update.assert_called_once()

    def test_denied_access_prevents_service_call_and_commit(self):
        """Denied access prevents update_item call and commit."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        session_id = uuid.uuid4()
        item_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.user_id = "other-user"

        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service, "update_item"
            ) as mock_update:
                with pytest.raises(AppException):
                    _run(
                        session_queue.update_queued_query(
                            session_id=session_id,
                            item_id=item_id,
                            request=mock_request,
                            actor=actor,
                            policy_engine=policy_engine,
                            db=mock_db,
                        )
                    )

        mock_update.assert_not_called()
        mock_db.commit.assert_not_called()


class TestDeleteQueuedQuery:
    """Tests for delete_queued_query endpoint."""

    def test_passes_actor_and_policy_engine_through_helper(self):
        """Endpoint passes Actor and PolicyEngine through ownership helper."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        session_id = uuid.uuid4()
        item_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.id = session_id
        db_session.user_id = "user-123"

        mock_item = MagicMock()
        mock_db = MagicMock()
        mock_response = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service,
                "cancel_item",
                return_value=mock_item,
            ) as mock_cancel:
                with patch.object(
                    session_queue.SessionQueueItemResponse,
                    "model_validate",
                    return_value=mock_response,
                ):
                    _run(
                        session_queue.delete_queued_query(
                            session_id=session_id,
                            item_id=item_id,
                            actor=actor,
                            policy_engine=policy_engine,
                            db=mock_db,
                        )
                    )

        policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "user-123"
        )
        mock_cancel.assert_called_once()

    def test_denied_access_prevents_service_call_and_commit(self):
        """Denied access prevents cancel_item call and commit."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        session_id = uuid.uuid4()
        item_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.user_id = "other-user"

        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service, "cancel_item"
            ) as mock_cancel:
                with pytest.raises(AppException):
                    _run(
                        session_queue.delete_queued_query(
                            session_id=session_id,
                            item_id=item_id,
                            actor=actor,
                            policy_engine=policy_engine,
                            db=mock_db,
                        )
                    )

        mock_cancel.assert_not_called()
        mock_db.commit.assert_not_called()


class TestSendQueuedQueryNow:
    """Tests for send_queued_query_now endpoint."""

    def test_passes_actor_and_policy_engine_through_helper(self):
        """Endpoint passes Actor and PolicyEngine through ownership helper."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        session_id = uuid.uuid4()
        item_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.id = session_id
        db_session.user_id = "user-123"

        mock_result = MagicMock()
        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service,
                "send_now",
                return_value=mock_result,
            ) as mock_send:
                _run(
                    session_queue.send_queued_query_now(
                        session_id=session_id,
                        item_id=item_id,
                        actor=actor,
                        policy_engine=policy_engine,
                        db=mock_db,
                    )
                )

        policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "user-123"
        )
        mock_send.assert_called_once()

    def test_denied_access_prevents_service_call_and_commit(self):
        """Denied access prevents send_now call and commit."""
        actor = Actor(user_id="user-123", auth_source="test")
        policy_engine = MagicMock()
        policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        session_id = uuid.uuid4()
        item_id = uuid.uuid4()
        db_session = MagicMock()
        db_session.user_id = "other-user"

        mock_db = MagicMock()

        with patch.object(
            session_queue.session_service, "get_session", return_value=db_session
        ):
            with patch.object(
                session_queue.session_queue_service, "send_now"
            ) as mock_send:
                with pytest.raises(AppException):
                    _run(
                        session_queue.send_queued_query_now(
                            session_id=session_id,
                            item_id=item_id,
                            actor=actor,
                            policy_engine=policy_engine,
                            db=mock_db,
                        )
                    )

        mock_send.assert_not_called()
        mock_db.commit.assert_not_called()
