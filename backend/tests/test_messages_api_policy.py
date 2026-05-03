"""Tests for messages API policy engine integration."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyDecision


def _run(coro):
    """Helper to run async coroutines without pytest-asyncio."""
    return asyncio.run(coro)


class TestGetMessagePolicy:
    """Tests for get_message endpoint policy enforcement."""

    def test_allowed_access_calls_message_service_with_actor_user_id(self):
        """When policy allows, message_service.get_message_response is called with actor.user_id."""
        from app.api.v1.messages import get_message

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_message = MagicMock()
        mock_message.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"  # Same as actor for allowed access

        with (
            patch(
                "app.api.v1.messages.message_service.get_message",
                return_value=mock_message,
            ) as mock_get_message,
            patch(
                "app.api.v1.messages.session_service.get_session",
                return_value=mock_db_session,
            ) as mock_get_session,
            patch(
                "app.api.v1.messages.message_service.get_message_response",
                return_value={"id": 1, "content": "test"},
            ) as mock_get_response,
        ):

            async def run_test():
                return await get_message(
                    message_id=1,
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        # Verify message fetched
        mock_get_message.assert_called_once_with(mock_db, 1)
        # Verify session fetched
        mock_get_session.assert_called_once_with(mock_db, "session-456")
        # Verify response fetched with actor.user_id
        mock_get_response.assert_called_once_with(mock_db, 1, user_id="actor-123")

    def test_policy_engine_receives_actor_and_session_owner(self):
        """Policy engine receives actor and session owner_user_id for decision."""
        from app.api.v1.messages import get_message

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_message = MagicMock()
        mock_message.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        with (
            patch(
                "app.api.v1.messages.message_service.get_message",
                return_value=mock_message,
            ),
            patch(
                "app.api.v1.messages.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.messages.message_service.get_message_response",
                return_value={"id": 1},
            ),
        ):

            async def run_test():
                return await get_message(
                    message_id=1,
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            _run(run_test())

        # Verify policy engine received correct arguments
        mock_policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "owner-789"
        )

    def test_denied_access_raises_forbidden_with_exact_message(self):
        """When policy denies, AppException with FORBIDDEN and exact message is raised."""
        from app.api.v1.messages import get_message

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_message = MagicMock()
        mock_message.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"  # Different from actor

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.messages.message_service.get_message",
                return_value=mock_message,
            ),
            patch(
                "app.api.v1.messages.session_service.get_session",
                return_value=mock_db_session,
            ),
        ):

            async def run_test():
                return await get_message(
                    message_id=1,
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException) as exc_info:
                _run(run_test())

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert exc_info.value.message == "Message does not belong to the user"

    def test_denied_access_prevents_message_service_call(self):
        """When policy denies, message_service.get_message_response is never called."""
        from app.api.v1.messages import get_message

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_message = MagicMock()
        mock_message.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.messages.message_service.get_message",
                return_value=mock_message,
            ),
            patch(
                "app.api.v1.messages.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.messages.message_service.get_message_response"
            ) as mock_get_response,
        ):

            async def run_test():
                return await get_message(
                    message_id=1,
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException):
                _run(run_test())

        # Verify get_message_response was never called
        mock_get_response.assert_not_called()
