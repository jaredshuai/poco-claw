from typing import Any, get_origin, get_args
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_config_preparer import (
    StagingRunDispatchConfigPreparer,
    RunDispatchConfigPreparer,
    ConfigResolverPort,
)


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


def test_constructor_annotations_use_protocols_not_any() -> None:
    """Assert constructor dependency parameters use Protocol types, not Any."""
    type_hints = StagingRunDispatchConfigPreparer.__init__.__annotations__

    dependency_params = [
        "backend_client",
        "config_resolver",
        "skill_stager",
        "plugin_stager",
        "attachment_stager",
        "claude_md_stager",
        "slash_command_stager",
        "subagent_stager",
    ]

    for param_name in dependency_params:
        assert param_name in type_hints, f"Missing annotation for {param_name}"
        annotation = type_hints[param_name]
        # Ensure annotation is not Any or Any-derived
        assert annotation is not Any, f"{param_name} should not be annotated with Any"
        # Ensure the annotation has a Protocol-like name (not raw Any)
        assert hasattr(annotation, "__name__"), (
            f"{param_name} annotation should be a named Protocol"
        )
        assert "Port" in annotation.__name__, (
            f"{param_name} should use a Protocol port type"
        )


def test_run_dispatch_config_preparer_prepare_config_param_is_dict_str_object() -> None:
    """Regression: prepare_config config_snapshot is dict[str, object], not dict[str, Any]."""
    hints = RunDispatchConfigPreparer.prepare_config.__type_params__
    # Protocol methods don't have __type_params__, need to inspect via get_type_hints on the Protocol
    import typing

    hints = typing.get_type_hints(RunDispatchConfigPreparer.prepare_config)
    config_param = hints.get("config_snapshot")
    assert config_param is not None, "config_snapshot parameter not found"

    origin = get_origin(config_param)
    assert origin is dict, f"Expected dict, got {origin}"

    args = get_args(config_param)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_config_resolver_port_resolve_param_is_dict_str_object() -> None:
    """Regression: ConfigResolverPort.resolve config_snapshot is dict[str, object]."""
    import typing

    hints = typing.get_type_hints(ConfigResolverPort.resolve)
    config_param = hints.get("config_snapshot")
    assert config_param is not None, "config_snapshot parameter not found"

    origin = get_origin(config_param)
    assert origin is dict, f"Expected dict, got {origin}"

    args = get_args(config_param)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_staging_preparer_prepare_config_param_is_dict_str_object() -> None:
    """Regression: StagingRunDispatchConfigPreparer.prepare_config config_snapshot is dict[str, object]."""
    import typing

    hints = typing.get_type_hints(StagingRunDispatchConfigPreparer.prepare_config)
    config_param = hints.get("config_snapshot")
    assert config_param is not None, "config_snapshot parameter not found"

    origin = get_origin(config_param)
    assert origin is dict, f"Expected dict, got {origin}"

    args = get_args(config_param)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"
