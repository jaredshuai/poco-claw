import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler.task_dispatcher import (
    TaskDispatchDependencies,
    TaskDispatcher,
    _extract_enabled_skill_names,
    build_task_dispatch_dependencies,
)


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


def test_build_task_dispatch_dependencies_accepts_adapter_factories() -> None:
    executor_client = MagicMock()
    backend_client = MagicMock()
    config_resolver = MagicMock()
    skill_stager = MagicMock()
    plugin_stager = MagicMock()
    attachment_stager = MagicMock()
    slash_command_stager = MagicMock()
    subagent_stager = MagicMock()

    with (
        patch(
            "app.scheduler.task_dispatcher.ExecutorClient",
            side_effect=AssertionError("default executor constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.BackendClient",
            side_effect=AssertionError("default backend constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.ConfigResolver",
            side_effect=AssertionError("default config resolver constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.SkillStager",
            side_effect=AssertionError("default skill stager constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.PluginStager",
            side_effect=AssertionError("default plugin stager constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.AttachmentStager",
            side_effect=AssertionError("default attachment stager constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.SlashCommandStager",
            side_effect=AssertionError("default slash command stager constructor used"),
        ),
        patch(
            "app.scheduler.task_dispatcher.SubAgentStager",
            side_effect=AssertionError("default subagent stager constructor used"),
        ),
    ):
        dependencies = build_task_dispatch_dependencies(
            executor_client_factory=lambda: executor_client,
            backend_client_factory=lambda: backend_client,
            config_resolver_factory=lambda backend: config_resolver,
            skill_stager_factory=lambda: skill_stager,
            plugin_stager_factory=lambda: plugin_stager,
            attachment_stager_factory=lambda: attachment_stager,
            slash_command_stager_factory=lambda: slash_command_stager,
            subagent_stager_factory=lambda: subagent_stager,
        )

    assert dependencies.executor_client is executor_client
    assert dependencies.backend_client is backend_client
    assert dependencies.config_resolver is config_resolver
    assert dependencies.skill_stager is skill_stager
    assert dependencies.plugin_stager is plugin_stager
    assert dependencies.attachment_stager is attachment_stager
    assert dependencies.slash_command_stager is slash_command_stager
    assert dependencies.subagent_stager is subagent_stager


class TestTaskDispatcherGetContainerPool(unittest.TestCase):
    """Test TaskDispatcher.get_container_pool."""

    def test_creates_pool_if_none(self) -> None:
        # Reset class variable
        TaskDispatcher.container_pool = None

        with patch("app.scheduler.task_dispatcher.ContainerPool") as mock_pool_cls:
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

    def test_get_container_pool_uses_injected_factory(self) -> None:
        TaskDispatcher.container_pool = None
        original_factory = TaskDispatcher.container_pool_factory
        mock_pool = MagicMock()
        TaskDispatcher.container_pool_factory = lambda: mock_pool

        try:
            with patch(
                "app.scheduler.task_dispatcher.ContainerPool",
                side_effect=AssertionError("container pool should be injected"),
            ):
                result = TaskDispatcher.get_container_pool()

            assert result is mock_pool
        finally:
            TaskDispatcher.container_pool = None
            TaskDispatcher.container_pool_factory = original_factory


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


@pytest.mark.asyncio
class TestTaskDispatcherDispatch:
    """Test TaskDispatcher.dispatch."""

    def setUp(self) -> None:
        TaskDispatcher.container_pool = None

    async def test_dispatch_uses_injected_dependencies(self) -> None:
        """Test dispatch uses caller-supplied dependencies instead of concrete adapters."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token-123"
            mock_settings_obj.executor_task_lease_secret = "lease-token"
            mock_settings.return_value = mock_settings_obj

            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock()

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(return_value={})

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(return_value={})

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(return_value={})

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

            dependencies = TaskDispatchDependencies(
                executor_client=mock_executor_client,
                backend_client=mock_backend_client,
                config_resolver=mock_config_resolver,
                skill_stager=mock_skill_stager,
                plugin_stager=mock_plugin_stager,
                attachment_stager=mock_attachment_stager,
                slash_command_stager=mock_slash_command_stager,
                subagent_stager=mock_subagent_stager,
            )

            with (
                patch(
                    "app.scheduler.task_dispatcher.build_task_dispatch_dependencies",
                    side_effect=AssertionError("dependencies should be injected"),
                ),
                patch.object(
                    TaskDispatcher,
                    "resolve_executor_target",
                    AsyncMock(return_value=("http://executor:8080", "container-123")),
                ),
            ):
                await TaskDispatcher.dispatch(
                    task_id="task-123",
                    session_id="session-456",
                    prompt="Hello",
                    config={"user_id": "user-789"},
                    dependencies=dependencies,
                )

            mock_executor_client.execute_task.assert_called_once()
            mock_backend_client.update_session_status.assert_called_once_with(
                "session-456", "running"
            )

    async def test_dispatch_uses_injected_runtime_boundary(self) -> None:
        """Test dispatch runtime allocation uses caller-supplied boundary."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token-123"
            mock_settings_obj.executor_task_lease_secret = "lease-token"
            mock_settings.return_value = mock_settings_obj

            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock()

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(return_value={})

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(return_value={})

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(return_value={})

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

            mock_runtime = MagicMock()
            mock_runtime.resolve_executor_target = AsyncMock(
                return_value=("http://executor:8080", "container-123")
            )
            mock_runtime.cancel_task = AsyncMock()

            dependencies = TaskDispatchDependencies(
                executor_client=mock_executor_client,
                backend_client=mock_backend_client,
                config_resolver=mock_config_resolver,
                skill_stager=mock_skill_stager,
                plugin_stager=mock_plugin_stager,
                attachment_stager=mock_attachment_stager,
                slash_command_stager=mock_slash_command_stager,
                subagent_stager=mock_subagent_stager,
                runtime=mock_runtime,
            )

            with (
                patch.object(
                    TaskDispatcher,
                    "resolve_executor_target",
                    AsyncMock(side_effect=AssertionError("runtime should be injected")),
                ),
                patch.object(
                    TaskDispatcher,
                    "get_container_pool",
                    side_effect=AssertionError("runtime should be injected"),
                ),
            ):
                await TaskDispatcher.dispatch(
                    task_id="task-123",
                    session_id="session-456",
                    prompt="Hello",
                    config={"user_id": "user-789"},
                    dependencies=dependencies,
                )

            mock_runtime.resolve_executor_target.assert_awaited_once_with(
                session_id="session-456",
                user_id="user-789",
                browser_enabled=False,
                container_mode="ephemeral",
                container_id=None,
            )
            mock_runtime.cancel_task.assert_not_awaited()
            mock_executor_client.execute_task.assert_awaited_once()

    async def test_dispatch_uses_injected_settings_boundary(self) -> None:
        """Test dispatch can receive settings without reading global settings."""
        settings = MagicMock()
        settings.callback_base_url = "http://callback"
        settings.callback_token = "token-123"
        settings.executor_task_lease_secret = "lease-token"

        mock_executor_client = MagicMock()
        mock_executor_client.execute_task = AsyncMock()

        mock_backend_client = MagicMock()
        mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
        mock_backend_client.update_session_status = AsyncMock()

        mock_config_resolver = MagicMock()
        mock_config_resolver.resolve = AsyncMock(return_value={})

        mock_skill_stager = MagicMock()
        mock_skill_stager.stage_skills = MagicMock(return_value={})

        mock_plugin_stager = MagicMock()
        mock_plugin_stager.stage_plugins = MagicMock(return_value={})

        mock_attachment_stager = MagicMock()
        mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

        mock_slash_command_stager = MagicMock()
        mock_slash_command_stager.stage_commands = MagicMock(return_value={})

        mock_subagent_stager = MagicMock()
        mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

        mock_runtime = MagicMock()
        mock_runtime.resolve_executor_target = AsyncMock(
            return_value=("http://executor:8080", "container-123")
        )
        mock_runtime.cancel_task = AsyncMock()

        dependencies = TaskDispatchDependencies(
            executor_client=mock_executor_client,
            backend_client=mock_backend_client,
            config_resolver=mock_config_resolver,
            skill_stager=mock_skill_stager,
            plugin_stager=mock_plugin_stager,
            attachment_stager=mock_attachment_stager,
            slash_command_stager=mock_slash_command_stager,
            subagent_stager=mock_subagent_stager,
            runtime=mock_runtime,
        )

        with patch(
            "app.scheduler.task_dispatcher.get_settings",
            side_effect=AssertionError("settings should be injected"),
        ):
            await TaskDispatcher.dispatch(
                task_id="task-123",
                session_id="session-456",
                prompt="Hello",
                config={"user_id": "user-789"},
                dependencies=dependencies,
                settings=settings,
            )

        call_kwargs = mock_executor_client.execute_task.call_args.kwargs
        assert call_kwargs["callback_url"] == "http://callback/api/v1/callback"
        assert call_kwargs["callback_token"] == "token-123"
        assert call_kwargs["task_lease_secret"] == "lease-token"

    async def test_dispatch_empty_callback_url(self) -> None:
        """Test dispatch raises ValueError when callback_base_url is empty."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = ""
            mock_settings_obj.callback_token = "token"
            mock_settings.return_value = mock_settings_obj

            # Mock all dependencies that are created before the check
            with patch("app.scheduler.task_dispatcher.ExecutorClient"):
                with patch("app.scheduler.task_dispatcher.BackendClient"):
                    with patch("app.scheduler.task_dispatcher.ConfigResolver"):
                        with patch("app.scheduler.task_dispatcher.SkillStager"):
                            with patch("app.scheduler.task_dispatcher.PluginStager"):
                                with patch(
                                    "app.scheduler.task_dispatcher.AttachmentStager"
                                ):
                                    with patch(
                                        "app.scheduler.task_dispatcher.SlashCommandStager"
                                    ):
                                        with patch(
                                            "app.scheduler.task_dispatcher.SubAgentStager"
                                        ):
                                            with pytest.raises(
                                                ValueError,
                                                match="callback_base_url cannot be empty",
                                            ):
                                                await TaskDispatcher.dispatch(
                                                    task_id="task-123",
                                                    session_id="session-456",
                                                    prompt="Hello",
                                                    config={"user_id": "user-789"},
                                                )

    async def test_dispatch_success(self) -> None:
        """Test successful dispatch flow."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token-123"
            mock_settings_obj.executor_task_lease_secret = "lease-token"
            mock_settings.return_value = mock_settings_obj

            # Mock all dependencies
            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock()

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(
                return_value={
                    "skill_files": {"skill1": {"content": "skill"}},
                    "plugin_files": {"plugin1": {"content": "plugin"}},
                    "input_files": [{"path": "/tmp/file.txt"}],
                    "browser_enabled": False,
                }
            )

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(
                return_value={"skill1": {"staged": True}}
            )

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(
                return_value={"plugin1": {"staged": True}}
            )

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(
                return_value=[{"staged": True}]
            )

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

            with patch(
                "app.scheduler.task_dispatcher.ExecutorClient",
                return_value=mock_executor_client,
            ):
                with patch(
                    "app.scheduler.task_dispatcher.BackendClient",
                    return_value=mock_backend_client,
                ):
                    with patch(
                        "app.scheduler.task_dispatcher.ConfigResolver",
                        return_value=mock_config_resolver,
                    ):
                        with patch(
                            "app.scheduler.task_dispatcher.SkillStager",
                            return_value=mock_skill_stager,
                        ):
                            with patch(
                                "app.scheduler.task_dispatcher.PluginStager",
                                return_value=mock_plugin_stager,
                            ):
                                with patch(
                                    "app.scheduler.task_dispatcher.AttachmentStager",
                                    return_value=mock_attachment_stager,
                                ):
                                    with patch(
                                        "app.scheduler.task_dispatcher.SlashCommandStager",
                                        return_value=mock_slash_command_stager,
                                    ):
                                        with patch(
                                            "app.scheduler.task_dispatcher.SubAgentStager",
                                            return_value=mock_subagent_stager,
                                        ):
                                            with patch.object(
                                                TaskDispatcher,
                                                "resolve_executor_target",
                                                AsyncMock(
                                                    return_value=(
                                                        "http://executor:8080",
                                                        "container-123",
                                                    )
                                                ),
                                            ):
                                                await TaskDispatcher.dispatch(
                                                    task_id="task-123",
                                                    session_id="session-456",
                                                    prompt="Hello",
                                                    config={"user_id": "user-789"},
                                                )

                                                mock_executor_client.execute_task.assert_called_once()
                                                call_kwargs = mock_executor_client.execute_task.call_args.kwargs
                                                assert (
                                                    call_kwargs["task_lease_secret"]
                                                    == "lease-token"
                                                )
                                                mock_backend_client.update_session_status.assert_called_once_with(
                                                    "session-456", "running"
                                                )

    async def test_dispatch_with_exception(self) -> None:
        """Test dispatch handles exception and updates session status."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token"
            mock_settings.return_value = mock_settings_obj

            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock(
                side_effect=RuntimeError("Executor failed")
            )

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(return_value={})

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(return_value={})

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(return_value={})

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

            mock_pool = MagicMock()
            mock_pool.cancel_task = AsyncMock()

            with patch(
                "app.scheduler.task_dispatcher.ExecutorClient",
                return_value=mock_executor_client,
            ):
                with patch(
                    "app.scheduler.task_dispatcher.BackendClient",
                    return_value=mock_backend_client,
                ):
                    with patch(
                        "app.scheduler.task_dispatcher.ConfigResolver",
                        return_value=mock_config_resolver,
                    ):
                        with patch(
                            "app.scheduler.task_dispatcher.SkillStager",
                            return_value=mock_skill_stager,
                        ):
                            with patch(
                                "app.scheduler.task_dispatcher.PluginStager",
                                return_value=mock_plugin_stager,
                            ):
                                with patch(
                                    "app.scheduler.task_dispatcher.AttachmentStager",
                                    return_value=mock_attachment_stager,
                                ):
                                    with patch(
                                        "app.scheduler.task_dispatcher.SlashCommandStager",
                                        return_value=mock_slash_command_stager,
                                    ):
                                        with patch(
                                            "app.scheduler.task_dispatcher.SubAgentStager",
                                            return_value=mock_subagent_stager,
                                        ):
                                            with patch.object(
                                                TaskDispatcher,
                                                "get_container_pool",
                                                return_value=mock_pool,
                                            ):
                                                with patch.object(
                                                    TaskDispatcher,
                                                    "resolve_executor_target",
                                                    AsyncMock(
                                                        return_value=(
                                                            "http://executor:8080",
                                                            "container-123",
                                                        )
                                                    ),
                                                ):
                                                    with pytest.raises(
                                                        RuntimeError,
                                                        match="Executor failed",
                                                    ):
                                                        await TaskDispatcher.dispatch(
                                                            task_id="task-123",
                                                            session_id="session-456",
                                                            prompt="Hello",
                                                            config={
                                                                "user_id": "user-789"
                                                            },
                                                        )

                                                    mock_backend_client.update_session_status.assert_called_with(
                                                        "session-456", "failed"
                                                    )
                                                    mock_pool.cancel_task.assert_called_once_with(
                                                        "session-456"
                                                    )

    async def test_dispatch_with_sdk_session_id(self) -> None:
        """Test dispatch with sdk_session_id parameter."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token"
            mock_settings.return_value = mock_settings_obj

            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock()

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(return_value={})

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(return_value={})

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(return_value={})

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

            with patch(
                "app.scheduler.task_dispatcher.ExecutorClient",
                return_value=mock_executor_client,
            ):
                with patch(
                    "app.scheduler.task_dispatcher.BackendClient",
                    return_value=mock_backend_client,
                ):
                    with patch(
                        "app.scheduler.task_dispatcher.ConfigResolver",
                        return_value=mock_config_resolver,
                    ):
                        with patch(
                            "app.scheduler.task_dispatcher.SkillStager",
                            return_value=mock_skill_stager,
                        ):
                            with patch(
                                "app.scheduler.task_dispatcher.PluginStager",
                                return_value=mock_plugin_stager,
                            ):
                                with patch(
                                    "app.scheduler.task_dispatcher.AttachmentStager",
                                    return_value=mock_attachment_stager,
                                ):
                                    with patch(
                                        "app.scheduler.task_dispatcher.SlashCommandStager",
                                        return_value=mock_slash_command_stager,
                                    ):
                                        with patch(
                                            "app.scheduler.task_dispatcher.SubAgentStager",
                                            return_value=mock_subagent_stager,
                                        ):
                                            with patch.object(
                                                TaskDispatcher,
                                                "resolve_executor_target",
                                                AsyncMock(
                                                    return_value=(
                                                        "http://executor:8080",
                                                        "container-123",
                                                    )
                                                ),
                                            ):
                                                await TaskDispatcher.dispatch(
                                                    task_id="task-123",
                                                    session_id="session-456",
                                                    prompt="Hello",
                                                    config={"user_id": "user-789"},
                                                    sdk_session_id="sdk-session-789",
                                                )

                                                call_kwargs = mock_executor_client.execute_task.call_args.kwargs
                                                assert (
                                                    call_kwargs["sdk_session_id"]
                                                    == "sdk-session-789"
                                                )

    async def test_dispatch_with_timing_logs(self) -> None:
        """Test dispatch logs timing information when enqueued_at is provided."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token"
            mock_settings.return_value = mock_settings_obj

            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock()

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(return_value={})

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(return_value={})

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(return_value={})

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(return_value={})

            with patch(
                "app.scheduler.task_dispatcher.ExecutorClient",
                return_value=mock_executor_client,
            ):
                with patch(
                    "app.scheduler.task_dispatcher.BackendClient",
                    return_value=mock_backend_client,
                ):
                    with patch(
                        "app.scheduler.task_dispatcher.ConfigResolver",
                        return_value=mock_config_resolver,
                    ):
                        with patch(
                            "app.scheduler.task_dispatcher.SkillStager",
                            return_value=mock_skill_stager,
                        ):
                            with patch(
                                "app.scheduler.task_dispatcher.PluginStager",
                                return_value=mock_plugin_stager,
                            ):
                                with patch(
                                    "app.scheduler.task_dispatcher.AttachmentStager",
                                    return_value=mock_attachment_stager,
                                ):
                                    with patch(
                                        "app.scheduler.task_dispatcher.SlashCommandStager",
                                        return_value=mock_slash_command_stager,
                                    ):
                                        with patch(
                                            "app.scheduler.task_dispatcher.SubAgentStager",
                                            return_value=mock_subagent_stager,
                                        ):
                                            with patch.object(
                                                TaskDispatcher,
                                                "resolve_executor_target",
                                                AsyncMock(
                                                    return_value=(
                                                        "http://executor:8080",
                                                        "container-123",
                                                    )
                                                ),
                                            ):
                                                import time

                                                enqueued_at = (
                                                    time.perf_counter() - 0.1
                                                )  # 100ms ago

                                                await TaskDispatcher.dispatch(
                                                    task_id="task-123",
                                                    session_id="session-456",
                                                    prompt="Hello",
                                                    config={"user_id": "user-789"},
                                                    enqueued_at=enqueued_at,
                                                )

                                                mock_executor_client.execute_task.assert_called_once()

    async def test_dispatch_subagent_stager_exception(self) -> None:
        """Test dispatch handles subagent stager exception gracefully."""
        with patch("app.scheduler.task_dispatcher.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.callback_base_url = "http://callback"
            mock_settings_obj.callback_token = "token"
            mock_settings.return_value = mock_settings_obj

            mock_executor_client = MagicMock()
            mock_executor_client.execute_task = AsyncMock()

            mock_backend_client = MagicMock()
            mock_backend_client.resolve_slash_commands = AsyncMock(return_value={})
            mock_backend_client.update_session_status = AsyncMock()

            mock_config_resolver = MagicMock()
            mock_config_resolver.resolve = AsyncMock(
                return_value={
                    "subagent_raw_agents": {"agent1": {"spec": {}}},
                }
            )

            mock_skill_stager = MagicMock()
            mock_skill_stager.stage_skills = MagicMock(return_value={})

            mock_plugin_stager = MagicMock()
            mock_plugin_stager.stage_plugins = MagicMock(return_value={})

            mock_attachment_stager = MagicMock()
            mock_attachment_stager.stage_inputs = MagicMock(return_value=[])

            mock_slash_command_stager = MagicMock()
            mock_slash_command_stager.stage_commands = MagicMock(return_value={})

            mock_subagent_stager = MagicMock()
            mock_subagent_stager.stage_raw_agents = MagicMock(
                side_effect=ValueError("Invalid agent")
            )

            with patch(
                "app.scheduler.task_dispatcher.ExecutorClient",
                return_value=mock_executor_client,
            ):
                with patch(
                    "app.scheduler.task_dispatcher.BackendClient",
                    return_value=mock_backend_client,
                ):
                    with patch(
                        "app.scheduler.task_dispatcher.ConfigResolver",
                        return_value=mock_config_resolver,
                    ):
                        with patch(
                            "app.scheduler.task_dispatcher.SkillStager",
                            return_value=mock_skill_stager,
                        ):
                            with patch(
                                "app.scheduler.task_dispatcher.PluginStager",
                                return_value=mock_plugin_stager,
                            ):
                                with patch(
                                    "app.scheduler.task_dispatcher.AttachmentStager",
                                    return_value=mock_attachment_stager,
                                ):
                                    with patch(
                                        "app.scheduler.task_dispatcher.SlashCommandStager",
                                        return_value=mock_slash_command_stager,
                                    ):
                                        with patch(
                                            "app.scheduler.task_dispatcher.SubAgentStager",
                                            return_value=mock_subagent_stager,
                                        ):
                                            with patch.object(
                                                TaskDispatcher,
                                                "resolve_executor_target",
                                                AsyncMock(
                                                    return_value=(
                                                        "http://executor:8080",
                                                        "container-123",
                                                    )
                                                ),
                                            ):
                                                # Should not raise - subagent exception is caught and logged
                                                await TaskDispatcher.dispatch(
                                                    task_id="task-123",
                                                    session_id="session-456",
                                                    prompt="Hello",
                                                    config={"user_id": "user-789"},
                                                )

                                                mock_executor_client.execute_task.assert_called_once()


if __name__ == "__main__":
    unittest.main()
