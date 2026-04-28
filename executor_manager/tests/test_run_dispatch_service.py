from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_service import RunDispatchService


def _make_dispatch_service() -> RunDispatchService:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
    )
    backend_client = MagicMock()
    backend_client.resolve_slash_commands = AsyncMock(return_value={})
    backend_client.get_claude_md = AsyncMock(return_value={})
    backend_client.record_mcp_transition = AsyncMock()
    backend_client.start_run = AsyncMock()
    backend_client.fail_run = AsyncMock()

    executor_client = MagicMock()
    executor_client.execute_task = AsyncMock()

    config_resolver = MagicMock()
    config_resolver.resolve = AsyncMock(
        return_value={
            "skill_files": {},
            "plugin_files": {},
            "input_files": [],
        }
    )

    container_pool = MagicMock()
    container_pool.get_or_create_container = AsyncMock(
        return_value=("http://executor.local", "container-123")
    )
    container_pool.cancel_task = AsyncMock()

    skill_stager = MagicMock()
    skill_stager.stage_skills = MagicMock(return_value={})
    plugin_stager = MagicMock()
    plugin_stager.stage_plugins = MagicMock(return_value={})
    attachment_stager = MagicMock()
    attachment_stager.stage_inputs = MagicMock(return_value=[])
    claude_md_stager = MagicMock()
    claude_md_stager.stage = MagicMock(return_value={})
    slash_command_stager = MagicMock()
    slash_command_stager.stage_commands = MagicMock(return_value=[])
    subagent_stager = MagicMock()
    subagent_stager.stage_raw_agents = MagicMock(return_value=[])

    return RunDispatchService(
        settings=settings,
        backend_client=backend_client,
        executor_client=executor_client,
        config_resolver=config_resolver,
        skill_stager=skill_stager,
        plugin_stager=plugin_stager,
        attachment_stager=attachment_stager,
        claude_md_stager=claude_md_stager,
        slash_command_stager=slash_command_stager,
        subagent_stager=subagent_stager,
        container_pool=container_pool,
    )


@pytest.mark.asyncio
async def test_dispatch_claim_fails_and_cancels_when_start_run_fails() -> None:
    service = _make_dispatch_service()
    service.backend_client.start_run.side_effect = RuntimeError("start failed")
    claim = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {},
    }

    await service.dispatch_claim(claim, worker_id="worker-1")

    service.executor_client.execute_task.assert_awaited_once()
    service.backend_client.fail_run.assert_awaited_once()
    fail_kwargs = service.backend_client.fail_run.call_args.kwargs
    assert fail_kwargs["run_id"] == "run-123"
    assert fail_kwargs["worker_id"] == "worker-1"
    assert "start failed" in fail_kwargs["error_message"]
    service.container_pool.cancel_task.assert_awaited_once_with("sess-123")
