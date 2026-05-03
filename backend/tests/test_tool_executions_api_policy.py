"""Tests for tool executions API policy engine integration."""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyDecision


def _run(coro):
    """Helper to run async coroutines without pytest-asyncio."""
    return asyncio.run(coro)


class TestGetToolExecutionPolicy:
    """Tests for get_tool_execution endpoint policy enforcement."""

    def test_allowed_access_calls_model_validate(self):
        """When policy allows, ToolExecutionResponse.model_validate is called."""
        from app.api.v1.tool_executions import get_tool_execution

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_execution = MagicMock()
        mock_execution.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"  # Same as actor for allowed access

        with (
            patch(
                "app.api.v1.tool_executions.tool_execution_service.get_tool_execution",
                return_value=mock_execution,
            ) as mock_get_execution,
            patch(
                "app.api.v1.tool_executions.session_service.get_session",
                return_value=mock_db_session,
            ) as mock_get_session,
            patch(
                "app.api.v1.tool_executions.ToolExecutionResponse.model_validate",
                return_value={"id": "test-id"},
            ) as mock_validate,
        ):

            async def run_test():
                return await get_tool_execution(
                    execution_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        # Verify execution fetched
        mock_get_execution.assert_called_once()
        # Verify session fetched
        mock_get_session.assert_called_once_with(mock_db, "session-456")
        # Verify model_validate called
        mock_validate.assert_called_once_with(mock_execution)

    def test_policy_engine_receives_actor_and_session_owner(self):
        """Policy engine receives actor and session owner_user_id for decision."""
        from app.api.v1.tool_executions import get_tool_execution

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_execution = MagicMock()
        mock_execution.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        with (
            patch(
                "app.api.v1.tool_executions.tool_execution_service.get_tool_execution",
                return_value=mock_execution,
            ),
            patch(
                "app.api.v1.tool_executions.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.tool_executions.ToolExecutionResponse.model_validate",
                return_value={"id": "test-id"},
            ),
        ):

            async def run_test():
                return await get_tool_execution(
                    execution_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
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
        from app.api.v1.tool_executions import get_tool_execution

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_execution = MagicMock()
        mock_execution.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"  # Different from actor

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.tool_executions.tool_execution_service.get_tool_execution",
                return_value=mock_execution,
            ),
            patch(
                "app.api.v1.tool_executions.session_service.get_session",
                return_value=mock_db_session,
            ),
        ):

            async def run_test():
                return await get_tool_execution(
                    execution_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException) as exc_info:
                _run(run_test())

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert exc_info.value.message == "Tool execution does not belong to the user"

    def test_denied_access_prevents_model_validate_call(self):
        """When policy denies, ToolExecutionResponse.model_validate is never called."""
        from app.api.v1.tool_executions import get_tool_execution

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_execution = MagicMock()
        mock_execution.session_id = "session-456"
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.tool_executions.tool_execution_service.get_tool_execution",
                return_value=mock_execution,
            ),
            patch(
                "app.api.v1.tool_executions.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.tool_executions.ToolExecutionResponse.model_validate"
            ) as mock_validate,
        ):

            async def run_test():
                return await get_tool_execution(
                    execution_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException):
                _run(run_test())

        # Verify model_validate was never called
        mock_validate.assert_not_called()
