"""Tests for internal actor boundary in user-scoped internal API routes."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.identity import Actor


def _run(coro):
    """Helper to run async coroutines without pytest-asyncio."""
    return asyncio.run(coro)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def mock_actor():
    """Mock Actor for internal token auth."""
    return Actor(
        user_id="test-user-123",
        tenant_id="tenant-456",
        roles=("admin",),
        scopes=("read", "write"),
        auth_source="internal_token",
    )


class TestInternalPluginConfig:
    """Tests for internal_plugin_config.resolve_plugin_config."""

    def test_resolve_plugin_config_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_plugin_config import resolve_plugin_config
        from app.schemas.plugin_config import PluginConfigResolveRequest

        request = PluginConfigResolveRequest(plugin_ids=[1, 2])

        with patch(
            "app.api.v1.internal_plugin_config.service.resolve_user_plugin_files"
        ) as mock_resolve:
            mock_resolve.return_value = {"1": "config-1"}

            _run(resolve_plugin_config(request=request, actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(
                db=mock_db,
                user_id="test-user-123",
                plugin_ids=[1, 2],
            )


class TestInternalSkillConfig:
    """Tests for internal_skill_config.resolve_skill_config."""

    def test_resolve_skill_config_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_skill_config import resolve_skill_config
        from app.schemas.skill_config import SkillConfigResolveRequest

        request = SkillConfigResolveRequest(skill_ids=[1])

        with patch(
            "app.api.v1.internal_skill_config.service.resolve_user_skill_files"
        ) as mock_resolve:
            mock_resolve.return_value = {"1": "config-1"}

            _run(resolve_skill_config(request=request, actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(
                db=mock_db, user_id="test-user-123", skill_ids=[1]
            )


class TestInternalMcpConfig:
    """Tests for internal_mcp_config.resolve_mcp_config."""

    def test_resolve_mcp_config_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_mcp_config import resolve_mcp_config
        from app.schemas.mcp_config import McpConfigResolveRequest

        request = McpConfigResolveRequest(server_ids=[1])

        with patch(
            "app.api.v1.internal_mcp_config.service.resolve_user_mcp_config"
        ) as mock_resolve:
            mock_resolve.return_value = {"servers": []}

            _run(resolve_mcp_config(request=request, actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(
                db=mock_db, user_id="test-user-123", server_ids=[1]
            )


class TestInternalSlashCommands:
    """Tests for internal_slash_commands.resolve_slash_commands."""

    def test_resolve_slash_commands_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_slash_commands import resolve_slash_commands
        from app.schemas.slash_command_config import SlashCommandResolveRequest

        request = SlashCommandResolveRequest(names=["cmd-1"], skill_names=[])

        with patch(
            "app.api.v1.internal_slash_commands.service.resolve_user_commands"
        ) as mock_resolve:
            mock_resolve.return_value = {"cmd-1": "definition"}

            _run(resolve_slash_commands(request=request, actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(
                mock_db,
                user_id="test-user-123",
                names=["cmd-1"],
                skill_names=[],
            )


class TestInternalSubagents:
    """Tests for internal_subagents.resolve_subagents."""

    def test_resolve_subagents_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_subagents import resolve_subagents
        from app.schemas.sub_agent import SubAgentResolveRequest

        request = SubAgentResolveRequest(subagent_ids=[1])

        with patch(
            "app.api.v1.internal_subagents.service.resolve_for_execution"
        ) as mock_resolve:
            mock_resolve.return_value = {"subagents": []}

            _run(resolve_subagents(request=request, actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(
                mock_db,
                user_id="test-user-123",
                subagent_ids=[1],
            )


class TestInternalExecutionSettings:
    """Tests for internal_execution_settings.resolve_execution_settings."""

    def test_resolve_execution_settings_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_execution_settings import resolve_execution_settings

        with patch(
            "app.api.v1.internal_execution_settings.service.resolve_for_execution"
        ) as mock_resolve:
            mock_resolve.return_value = {"setting": "value"}

            _run(resolve_execution_settings(actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(mock_db, "test-user-123")


class TestInternalEnvVars:
    """Tests for internal_env_vars.get_env_map."""

    def test_get_env_map_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_env_vars import get_env_map

        with patch(
            "app.api.v1.internal_env_vars.env_var_service.get_env_map"
        ) as mock_resolve:
            mock_resolve.return_value = {"KEY": "value"}

            _run(get_env_map(actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(mock_db, user_id="test-user-123")


class TestInternalClaudeMd:
    """Tests for internal_claude_md.get_claude_md_internal."""

    def test_get_claude_md_internal_uses_actor_user_id(self, mock_db, mock_actor):
        from app.api.v1.internal_claude_md import get_claude_md_internal

        with patch(
            "app.api.v1.internal_claude_md.service.get_settings"
        ) as mock_resolve:
            mock_resolve.return_value = {"content": "# CLAUDE.md"}

            _run(get_claude_md_internal(actor=mock_actor, db=mock_db))

            mock_resolve.assert_called_once_with(mock_db, user_id="test-user-123")


class TestNoGetCurrentUserIdImport:
    """Static/import test that migrated modules no longer expose get_current_user_id."""

    def test_internal_plugin_config_no_get_current_user_id(self):
        import app.api.v1.internal_plugin_config as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_skill_config_no_get_current_user_id(self):
        import app.api.v1.internal_skill_config as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_mcp_config_no_get_current_user_id(self):
        import app.api.v1.internal_mcp_config as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_slash_commands_no_get_current_user_id(self):
        import app.api.v1.internal_slash_commands as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_subagents_no_get_current_user_id(self):
        import app.api.v1.internal_subagents as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_execution_settings_no_get_current_user_id(self):
        import app.api.v1.internal_execution_settings as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_env_vars_no_get_current_user_id(self):
        import app.api.v1.internal_env_vars as mod

        assert not hasattr(mod, "get_current_user_id")

    def test_internal_claude_md_no_get_current_user_id(self):
        import app.api.v1.internal_claude_md as mod

        assert not hasattr(mod, "get_current_user_id")
