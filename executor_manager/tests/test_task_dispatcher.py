import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler.task_dispatcher import TaskDispatcher, _extract_enabled_skill_names


class TestExtractEnabledSkillNames(unittest.TestCase):
    """Test _extract_enabled_skill_names helper function."""

    def test_empty_dict(self) -> None:
        result = _extract_enabled_skill_names({})
        assert result == []

    def test_non_dict_input(self) -> None:
        result = _extract_enabled_skill_names("not a dict")
        assert result == []

    def test_none_input(self) -> None:
        result = _extract_enabled_skill_names(None)
        assert result == []

    def test_single_skill_enabled(self) -> None:
        skills = {"skill1": {"enabled": True}}
        result = _extract_enabled_skill_names(skills)
        assert result == ["skill1"]

    def test_single_skill_no_enabled_field(self) -> None:
        skills = {"skill1": {}}
        result = _extract_enabled_skill_names(skills)
        assert result == ["skill1"]

    def test_skill_disabled(self) -> None:
        skills = {"skill1": {"enabled": False}}
        result = _extract_enabled_skill_names(skills)
        assert result == []

    def test_multiple_skills_mixed(self) -> None:
        skills = {
            "zebra": {"enabled": True},
            "alpha": {"enabled": True},
            "beta": {"enabled": False},
            "gamma": {},
        }
        result = _extract_enabled_skill_names(skills)
        # Should be sorted
        assert result == ["alpha", "gamma", "zebra"]

    def test_non_string_skill_name(self) -> None:
        skills = {123: {"enabled": True}}
        result = _extract_enabled_skill_names(skills)
        assert result == []

    def test_empty_skill_name(self) -> None:
        skills = {"": {"enabled": True}, "  ": {"enabled": True}}
        result = _extract_enabled_skill_names(skills)
        assert result == []

    def test_skill_name_with_whitespace(self) -> None:
        skills = {"  skill1  ": {"enabled": True}}
        result = _extract_enabled_skill_names(skills)
        assert result == ["skill1"]

    def test_non_dict_spec(self) -> None:
        skills = {"skill1": "not a dict"}
        result = _extract_enabled_skill_names(skills)
        assert result == ["skill1"]

    def test_enabled_is_not_false(self) -> None:
        skills = {"skill1": {"enabled": "true"}}
        result = _extract_enabled_skill_names(skills)
        assert result == ["skill1"]


class TestTaskDispatcherGetContainerPool(unittest.TestCase):
    """Test TaskDispatcher.get_container_pool."""

    def test_creates_pool_if_none(self) -> None:
        # Reset class variable
        TaskDispatcher.container_pool = None

        with patch(
            "app.scheduler.task_dispatcher.ContainerPool"
        ) as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value = mock_pool

            result = TaskDispatcher.get_container_pool()

            assert result == mock_pool
            mock_pool_cls.assert_called_once()

        # Clean up
        TaskDispatcher.container_pool = None

    def test_returns_existing_pool(self) -> None:
        mock_pool = MagicMock()
        TaskDispatcher.container_pool = mock_pool

        result = TaskDispatcher.get_container_pool()

        assert result == mock_pool

        # Clean up
        TaskDispatcher.container_pool = None


@pytest.mark.asyncio
class TestTaskDispatcherResolveExecutorTarget:
    """Test TaskDispatcher.resolve_executor_target."""

    async def test_resolve_executor_target(self) -> None:
        TaskDispatcher.container_pool = None

        mock_pool = MagicMock()
        mock_pool.get_or_create_container = AsyncMock(
            return_value=("http://executor:8080", "container-123")
        )

        with patch(
            "app.scheduler.task_dispatcher.ContainerPool",
            return_value=mock_pool,
        ):
            TaskDispatcher.container_pool = mock_pool

            result = await TaskDispatcher.resolve_executor_target(
                session_id="session-123",
                user_id="user-456",
                browser_enabled=True,
                container_mode="ephemeral",
                container_id=None,
            )

            assert result == ("http://executor:8080", "container-123")
            mock_pool.get_or_create_container.assert_called_once_with(
                session_id="session-123",
                user_id="user-456",
                browser_enabled=True,
                container_mode="ephemeral",
                container_id=None,
            )

        # Clean up
        TaskDispatcher.container_pool = None


@pytest.mark.asyncio
class TestTaskDispatcherOnTaskComplete:
    """Test TaskDispatcher.on_task_complete."""

    async def test_on_task_complete(self) -> None:
        mock_pool = MagicMock()
        mock_pool.on_task_complete = AsyncMock()

        TaskDispatcher.container_pool = mock_pool

        await TaskDispatcher.on_task_complete("session-123")

        mock_pool.on_task_complete.assert_called_once_with("session-123")

        # Clean up
        TaskDispatcher.container_pool = None


if __name__ == "__main__":
    unittest.main()