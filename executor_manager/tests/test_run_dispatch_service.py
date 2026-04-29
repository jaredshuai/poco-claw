from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch

import pytest

from app.services.run_dispatch_service import RunDispatchService


def _make_dispatch_service() -> RunDispatchService:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
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


def test_create_default_accepts_adapter_factories() -> None:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )
    backend_client = MagicMock()
    executor_client = MagicMock()
    config_resolver = MagicMock()
    skill_stager = MagicMock()
    plugin_stager = MagicMock()
    attachment_stager = MagicMock()
    claude_md_stager = MagicMock()
    slash_command_stager = MagicMock()
    subagent_stager = MagicMock()

    with (
        patch(
            "app.services.run_dispatch_service.BackendClient",
            side_effect=AssertionError("default backend constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.ExecutorClient",
            side_effect=AssertionError("default executor constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.ConfigResolver",
            side_effect=AssertionError("default config resolver constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.SkillStager",
            side_effect=AssertionError("default skill stager constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.PluginStager",
            side_effect=AssertionError("default plugin stager constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.AttachmentStager",
            side_effect=AssertionError("default attachment stager constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.ClaudeMdStager",
            side_effect=AssertionError("default claude md stager constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.SlashCommandStager",
            side_effect=AssertionError("default slash command stager constructor used"),
        ),
        patch(
            "app.services.run_dispatch_service.SubAgentStager",
            side_effect=AssertionError("default subagent stager constructor used"),
        ),
    ):
        service = RunDispatchService.create_default(
            settings=settings,
            backend_client_factory=lambda: backend_client,
            executor_client_factory=lambda: executor_client,
            config_resolver_factory=lambda backend: config_resolver,
            skill_stager_factory=lambda: skill_stager,
            plugin_stager_factory=lambda: plugin_stager,
            attachment_stager_factory=lambda: attachment_stager,
            claude_md_stager_factory=lambda: claude_md_stager,
            slash_command_stager_factory=lambda: slash_command_stager,
            subagent_stager_factory=lambda: subagent_stager,
        )

    assert service.settings is settings
    assert service.backend_client is backend_client
    assert service.executor_client is executor_client
    assert service.config_resolver is config_resolver
    assert service.skill_stager is skill_stager
    assert service.plugin_stager is plugin_stager
    assert service.attachment_stager is attachment_stager
    assert service.claude_md_stager is claude_md_stager
    assert service.slash_command_stager is slash_command_stager
    assert service.subagent_stager is subagent_stager


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

    service.executor_client.execute_task.assert_not_awaited()
    service.backend_client.fail_run.assert_awaited_once()
    fail_kwargs = service.backend_client.fail_run.call_args.kwargs
    assert fail_kwargs["run_id"] == "run-123"
    assert fail_kwargs["worker_id"] == "worker-1"
    assert "start failed" in fail_kwargs["error_message"]
    service.container_pool.cancel_task.assert_awaited_once_with("sess-123")


@pytest.mark.asyncio
async def test_dispatch_claim_starts_run_before_executor_execute_task() -> None:
    service = _make_dispatch_service()
    call_order: list[str] = []

    async def start_run(*, run_id: str, worker_id: str) -> None:
        call_order.append(f"start:{run_id}:{worker_id}")

    async def execute_task(**kwargs) -> str:
        call_order.append(f"execute:{kwargs['run_id']}")
        return "sess-123"

    service.backend_client.start_run.side_effect = start_run
    service.executor_client.execute_task.side_effect = execute_task
    claim = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {},
    }

    await service.dispatch_claim(claim, worker_id="worker-1")

    assert call_order == ["start:run-123:worker-1", "execute:run-123"]


@pytest.mark.asyncio
async def test_dispatch_claim_passes_dedicated_task_lease_secret() -> None:
    service = _make_dispatch_service()
    claim = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {},
    }

    await service.dispatch_claim(claim, worker_id="worker-1")

    service.executor_client.execute_task.assert_awaited_once()
    call_kwargs = service.executor_client.execute_task.call_args.kwargs
    assert call_kwargs["callback_token"] == "callback-token"
    assert call_kwargs["task_lease_secret"] == "lease-secret"
