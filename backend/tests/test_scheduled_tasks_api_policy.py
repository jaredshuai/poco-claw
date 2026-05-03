"""Tests for scheduled tasks API policy engine integration."""

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


class TestCreateScheduledTaskPolicy:
    """Tests for create_scheduled_task endpoint policy enforcement."""

    def test_passes_actor_user_id_to_service(self):
        """create_scheduled_task passes actor.user_id to ScheduledTaskService."""
        from app.api.v1.scheduled_tasks import create_scheduled_task

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_request = MagicMock()

        with patch(
            "app.api.v1.scheduled_tasks.scheduled_task_service.create_task",
            return_value={"id": "task-456"},
        ) as mock_create_task:

            async def run_test():
                return await create_scheduled_task(
                    request=mock_request,
                    actor=actor,
                    db=mock_db,
                )

            _run(run_test())

        # Verify service called with actor.user_id
        mock_create_task.assert_called_once_with(mock_db, "actor-123", mock_request)


class TestListScheduledTaskRunsPolicy:
    """Tests for list_scheduled_task_runs endpoint policy enforcement."""

    def test_allowed_access_calls_repositories(self):
        """When policy allows, RunRepository and UsageService are called."""
        from app.api.v1.scheduled_tasks import list_scheduled_task_runs

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_task = MagicMock()
        mock_task.user_id = "actor-123"  # Same as actor for allowed access
        mock_run = MagicMock()
        mock_run.id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with (
            patch(
                "app.api.v1.scheduled_tasks.ScheduledTaskRepository.get_by_id",
                return_value=mock_task,
            ) as mock_get_task,
            patch(
                "app.api.v1.scheduled_tasks.RunRepository.list_by_scheduled_task",
                return_value=[mock_run],
            ) as mock_list_runs,
            patch(
                "app.api.v1.scheduled_tasks.usage_service.get_usage_summaries_by_run_ids",
                return_value={},
            ) as mock_get_usage,
            patch(
                "app.api.v1.scheduled_tasks.RunResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):

            async def run_test():
                return await list_scheduled_task_runs(
                    task_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=MagicMock(
                        can_access_user_resource=MagicMock(
                            return_value=PolicyDecision(allowed=True)
                        )
                    ),
                    db=mock_db,
                )

            _run(run_test())

        # Verify task fetched
        mock_get_task.assert_called_once()
        # Verify runs fetched
        mock_list_runs.assert_called_once()
        # Verify usage fetched
        mock_get_usage.assert_called_once()

    def test_policy_engine_receives_actor_and_task_owner(self):
        """Policy engine receives actor and db_task.user_id for decision."""
        from app.api.v1.scheduled_tasks import list_scheduled_task_runs

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_task = MagicMock()
        mock_task.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=True
        )

        with (
            patch(
                "app.api.v1.scheduled_tasks.ScheduledTaskRepository.get_by_id",
                return_value=mock_task,
            ),
            patch(
                "app.api.v1.scheduled_tasks.RunRepository.list_by_scheduled_task",
                return_value=[],
            ),
            patch(
                "app.api.v1.scheduled_tasks.usage_service.get_usage_summaries_by_run_ids",
                return_value={},
            ),
        ):

            async def run_test():
                return await list_scheduled_task_runs(
                    task_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
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
        from app.api.v1.scheduled_tasks import list_scheduled_task_runs

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_task = MagicMock()
        mock_task.user_id = "owner-789"  # Different from actor

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.scheduled_tasks.ScheduledTaskRepository.get_by_id",
                return_value=mock_task,
            ),
        ):

            async def run_test():
                return await list_scheduled_task_runs(
                    task_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException) as exc_info:
                _run(run_test())

        assert exc_info.value.error_code == ErrorCode.FORBIDDEN
        assert exc_info.value.message == "Scheduled task does not belong to the user"

    def test_denied_access_prevents_repository_calls(self):
        """When policy denies, RunRepository and UsageService are never called."""
        from app.api.v1.scheduled_tasks import list_scheduled_task_runs

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_task = MagicMock()
        mock_task.user_id = "owner-789"

        mock_policy_engine = MagicMock()
        mock_policy_engine.can_access_user_resource.return_value = PolicyDecision(
            allowed=False, reason="user_owner_mismatch"
        )

        with (
            patch(
                "app.api.v1.scheduled_tasks.ScheduledTaskRepository.get_by_id",
                return_value=mock_task,
            ),
            patch(
                "app.api.v1.scheduled_tasks.RunRepository.list_by_scheduled_task"
            ) as mock_list_runs,
            patch(
                "app.api.v1.scheduled_tasks.usage_service.get_usage_summaries_by_run_ids"
            ) as mock_get_usage,
        ):

            async def run_test():
                return await list_scheduled_task_runs(
                    task_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException):
                _run(run_test())

        # Verify repositories were never called
        mock_list_runs.assert_not_called()
        mock_get_usage.assert_not_called()

    def test_not_found_does_not_call_policy_engine(self):
        """When task is not found, NOT_FOUND is raised without calling policy engine."""
        from app.api.v1.scheduled_tasks import list_scheduled_task_runs

        actor = Actor(user_id="actor-123")
        mock_db = MagicMock()
        mock_policy_engine = MagicMock()

        with patch(
            "app.api.v1.scheduled_tasks.ScheduledTaskRepository.get_by_id",
            return_value=None,
        ):

            async def run_test():
                return await list_scheduled_task_runs(
                    task_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                    actor=actor,
                    policy_engine=mock_policy_engine,
                    db=mock_db,
                )

            with pytest.raises(AppException) as exc_info:
                _run(run_test())

        # Verify NOT_FOUND error
        assert exc_info.value.error_code == ErrorCode.NOT_FOUND
        # Verify policy engine was never called
        mock_policy_engine.can_access_user_resource.assert_not_called()
