from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_config_preparer import StagingRunDispatchConfigPreparer


@pytest.mark.asyncio
async def test_prepare_config_resolves_and_stages_executor_assets() -> None:
    backend_client = MagicMock()
    backend_client.resolve_slash_commands = AsyncMock(return_value=[{"name": "cmd"}])
    backend_client.get_claude_md = AsyncMock(
        return_value={"enabled": True, "content": "project instructions"}
    )
    config_resolver = MagicMock()
    config_resolver.resolve = AsyncMock(
        return_value={
            "skill_files": {"skill-a": {"content": "skill"}},
            "plugin_files": {"plugin-a": {"content": "plugin"}},
            "input_files": [{"path": "/tmp/input.txt"}],
            "subagent_raw_agents": {"agent-a": {"content": "agent"}},
        }
    )
    skill_stager = MagicMock()
    skill_stager.stage_skills.return_value = {"skill-a": {"staged": True}}
    plugin_stager = MagicMock()
    plugin_stager.stage_plugins.return_value = {"plugin-a": {"staged": True}}
    attachment_stager = MagicMock()
    attachment_stager.stage_inputs.return_value = [{"path": "/workspace/input.txt"}]
    claude_md_stager = MagicMock()
    claude_md_stager.stage.return_value = {"enabled": True, "bytes": 20}
    slash_command_stager = MagicMock()
    slash_command_stager.stage_commands.return_value = [{"name": "cmd", "staged": True}]
    subagent_stager = MagicMock()
    subagent_stager.stage_raw_agents.return_value = [{"name": "agent-a"}]
    preparer = StagingRunDispatchConfigPreparer(
        backend_client=backend_client,
        config_resolver=config_resolver,
        skill_stager=skill_stager,
        plugin_stager=plugin_stager,
        attachment_stager=attachment_stager,
        claude_md_stager=claude_md_stager,
        slash_command_stager=slash_command_stager,
        subagent_stager=subagent_stager,
    )

    resolved = await preparer.prepare_config(
        user_id="user-1",
        session_id="sess-1",
        run_id="run-1",
        config_snapshot={"container_mode": "persistent"},
    )

    assert resolved["skill_files"] == {"skill-a": {"staged": True}}
    assert resolved["plugin_files"] == {"plugin-a": {"staged": True}}
    assert resolved["input_files"] == [{"path": "/workspace/input.txt"}]
    assert "subagent_raw_agents" not in resolved
    backend_client.resolve_slash_commands.assert_awaited_once_with(
        user_id="user-1", skill_names=["skill-a"]
    )
    slash_command_stager.stage_commands.assert_called_once_with(
        user_id="user-1",
        session_id="sess-1",
        commands=[{"name": "cmd"}],
    )
    claude_md_stager.stage.assert_called_once_with(
        user_id="user-1",
        session_id="sess-1",
        enabled=True,
        content="project instructions",
    )
    subagent_stager.stage_raw_agents.assert_called_once_with(
        user_id="user-1",
        session_id="sess-1",
        raw_agents={"agent-a": {"content": "agent"}},
    )
