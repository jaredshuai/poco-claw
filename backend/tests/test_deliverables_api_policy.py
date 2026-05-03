"""Tests for deliverables API policy engine integration."""

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


class TestEnsureSessionOwner:
    """Tests for _ensure_session_owner helper function."""

    def test_passes_actor_and_session_owner_to_policy_engine(self):
        """_ensure_session_owner passes actor and session owner_user_id to policy engine."""
        from app.api.v1.deliverables import _ensure_session_owner

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        with patch(
            "app.api.v1.deliverables.session_service.get_session",
            return_value=mock_db_session,
        ):
            _ensure_session_owner(
                mock_db,
                uuid.UUID("00000000-0000-0000-0000-000000000001"),
                actor,
                mock_policy_engine,
            )

        mock_policy_engine.can_access_user_resource.assert_called_once_with(
            actor, "owner-789"
        )

    def test_denied_policy_raises_forbidden_with_exact_message(self):
        """When policy denies, AppException with FORBIDDEN and exact message is raised."""
        from app.api.v1.deliverables import _ensure_session_owner

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with patch(
            "app.api.v1.deliverables.session_service.get_session",
            return_value=mock_db_session,
        ):
            with pytest.raises(AppException) as exc_info:
                _ensure_session_owner(
                    mock_db,
                    uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    actor,
                    mock_policy_engine,
                )

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert exc_info.value.message == "Session does not belong to the user"


class TestListSessionDeliverablesPolicy:
    """Tests for list_session_deliverables endpoint policy enforcement."""

    def test_allowed_access_calls_deliverable_service(self):
        """When policy allows, deliverable_service.list_by_session is called."""
        from app.api.v1.deliverables import list_session_deliverables

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.list_by_session",
                return_value=[],
            ) as mock_list,
        ):

            async def run_test():
                return await list_session_deliverables(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        mock_list.assert_called_once()

    def test_denied_access_prevents_deliverable_service_call(self):
        """When policy denies, deliverable_service.list_by_session is never called."""
        from app.api.v1.deliverables import list_session_deliverables

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.list_by_session"
            ) as mock_list,
        ):

            async def run_test():
                return await list_session_deliverables(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException):
                _run(run_test())

        mock_list.assert_not_called()


class TestGetSessionDeliverablePolicy:
    """Tests for get_session_deliverable endpoint policy enforcement."""

    def test_allowed_access_calls_deliverable_service(self):
        """When policy allows, deliverable_service.get_deliverable is called."""
        from app.api.v1.deliverables import get_session_deliverable

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.get_deliverable",
                return_value=MagicMock(),
            ) as mock_get,
        ):

            async def run_test():
                return await get_session_deliverable(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    deliverable_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        mock_get.assert_called_once()

    def test_denied_access_prevents_deliverable_service_call(self):
        """When policy denies, deliverable_service.get_deliverable is never called."""
        from app.api.v1.deliverables import get_session_deliverable

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.get_deliverable"
            ) as mock_get,
        ):

            async def run_test():
                return await get_session_deliverable(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    deliverable_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException):
                _run(run_test())

        mock_get.assert_not_called()


class TestListSessionDeliverableVersionsPolicy:
    """Tests for list_session_deliverable_versions endpoint policy enforcement."""

    def test_allowed_access_calls_deliverable_service(self):
        """When policy allows, deliverable_service.list_versions_by_deliverable is called."""
        from app.api.v1.deliverables import list_session_deliverable_versions

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.list_versions_by_deliverable",
                return_value=[],
            ) as mock_list,
        ):

            async def run_test():
                return await list_session_deliverable_versions(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    deliverable_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        mock_list.assert_called_once()


class TestGetSessionDeliverableVersionPolicy:
    """Tests for get_session_deliverable_version endpoint policy enforcement."""

    def test_allowed_access_calls_deliverable_service(self):
        """When policy allows, deliverable_service.get_version is called."""
        from app.api.v1.deliverables import get_session_deliverable_version

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.get_version",
                return_value=MagicMock(),
            ) as mock_get,
        ):

            async def run_test():
                return await get_session_deliverable_version(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        mock_get.assert_called_once()


class TestGetSessionDeliverableVersionToolExecutionsPolicy:
    """Tests for get_session_deliverable_version_tool_executions endpoint policy enforcement."""

    def test_allowed_access_calls_deliverable_service(self):
        """When policy allows, deliverable_service.get_version_tool_executions is called."""
        from app.api.v1.deliverables import (
            get_session_deliverable_version_tool_executions,
        )

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.user_id = "actor-123"

        with (
            patch(
                "app.api.v1.deliverables.session_service.get_session",
                return_value=mock_db_session,
            ),
            patch(
                "app.api.v1.deliverables.deliverable_service.get_version_tool_executions",
                return_value=[],
            ) as mock_get,
        ):

            async def run_test():
                return await get_session_deliverable_version_tool_executions(
                    session_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        mock_get.assert_called_once()
