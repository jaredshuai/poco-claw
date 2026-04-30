from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch

import pytest

from app.services.run_dispatch_service import RunDispatchService


def _make_dispatch_service(
    *, runtime: object | None = None, config_preparer: object | None = None
) -> RunDispatchService:
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
        runtime=runtime,
        config_preparer=config_preparer,
    )


@pytest.mark.asyncio
async def test_dispatch_claim_delegates_runtime_allocation_to_injected_runtime() -> (
    None
):
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=("http://runtime-executor.local", "runtime-container-1")
    )
    runtime.cancel_runtime = AsyncMock()
    service = _make_dispatch_service(runtime=runtime)
    service.config_resolver.resolve.return_value = {
        "skill_files": {},
        "plugin_files": {},
        "input_files": [],
        "browser_enabled": True,
    }
    service.container_pool.get_or_create_container.side_effect = AssertionError(
        "container pool should stay behind runtime port"
    )
    claim = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {
            "container_mode": "persistent",
            "container_id": "existing-container",
            "browser_enabled": True,
        },
    }

    await service.dispatch_claim(claim, worker_id="worker-1")

    runtime.allocate_runtime.assert_awaited_once_with(
        session_id="sess-123",
        user_id="user-123",
        browser_enabled=True,
        container_mode="persistent",
        container_id="existing-container",
    )
    service.executor_client.execute_task.assert_awaited_once()
    assert (
        service.executor_client.execute_task.call_args.kwargs["executor_url"]
        == "http://runtime-executor.local"
    )


@pytest.mark.asyncio
async def test_dispatch_claim_cancels_injected_runtime_when_start_run_fails() -> None:
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=("http://runtime-executor.local", "runtime-container-1")
    )
    runtime.cancel_runtime = AsyncMock()
    service = _make_dispatch_service(runtime=runtime)
    service.backend_client.start_run.side_effect = RuntimeError("start failed")
    service.container_pool.cancel_task.side_effect = AssertionError(
        "runtime port should own cancellation"
    )
    claim = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {},
    }

    await service.dispatch_claim(claim, worker_id="worker-1")

    runtime.cancel_runtime.assert_awaited_once_with("sess-123")


@pytest.mark.asyncio
async def test_dispatch_claim_delegates_config_preparation_to_injected_port() -> None:
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=("http://runtime-executor.local", "runtime-container-1")
    )
    runtime.cancel_runtime = AsyncMock()
    config_preparer = MagicMock()
    config_preparer.prepare_config = AsyncMock(
        return_value={
            "skill_files": {},
            "plugin_files": {},
            "input_files": [],
            "browser_enabled": True,
        }
    )
    service = _make_dispatch_service(runtime=runtime, config_preparer=config_preparer)
    service.config_resolver.resolve.side_effect = AssertionError(
        "config resolver should stay behind config preparer port"
    )
    service.skill_stager.stage_skills.side_effect = AssertionError(
        "skill stager should stay behind config preparer port"
    )
    claim = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {"container_mode": "persistent"},
    }

    await service.dispatch_claim(claim, worker_id="worker-1")

    config_preparer.prepare_config.assert_awaited_once_with(
        user_id="user-123",
        session_id="sess-123",
        run_id="run-123",
        config_snapshot={"container_mode": "persistent"},
    )
    runtime.allocate_runtime.assert_awaited_once_with(
        session_id="sess-123",
        user_id="user-123",
        browser_enabled=True,
        container_mode="persistent",
        container_id=None,
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
            config_resolver_factory=lambda backend, settings: config_resolver,
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


def test_create_default_defers_default_adapter_construction() -> None:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )

    with (
        patch(
            "app.services.run_dispatch_service.BackendClient",
            side_effect=AssertionError("backend client should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.ExecutorClient",
            side_effect=AssertionError("executor client should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.ConfigResolver",
            side_effect=AssertionError("config resolver should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.SkillStager",
            side_effect=AssertionError("skill stager should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.PluginStager",
            side_effect=AssertionError("plugin stager should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.AttachmentStager",
            side_effect=AssertionError("attachment stager should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.ClaudeMdStager",
            side_effect=AssertionError("claude md stager should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.SlashCommandStager",
            side_effect=AssertionError("slash command stager should be lazy"),
        ),
        patch(
            "app.services.run_dispatch_service.SubAgentStager",
            side_effect=AssertionError("subagent stager should be lazy"),
        ),
    ):
        service = RunDispatchService.create_default(settings=settings)

    assert service.settings is settings


def test_create_default_passes_settings_to_default_config_resolver() -> None:
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

    with patch(
        "app.services.run_dispatch_service.ConfigResolver",
        return_value=config_resolver,
    ) as config_resolver_cls:
        service = RunDispatchService.create_default(
            settings=settings,
            backend_client=backend_client,
            executor_client=executor_client,
            skill_stager=skill_stager,
            plugin_stager=plugin_stager,
            attachment_stager=attachment_stager,
            claude_md_stager=claude_md_stager,
            slash_command_stager=slash_command_stager,
            subagent_stager=subagent_stager,
        )

        config_resolver_cls.assert_not_called()
        assert service.config_resolver is config_resolver
        config_resolver_cls.assert_called_once_with(backend_client, settings=settings)


def test_create_default_uses_injected_settings_without_loading_global_settings() -> (
    None
):
    settings = MagicMock(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )
    settings.__bool__.return_value = False
    backend_client = MagicMock()
    executor_client = MagicMock()
    config_resolver = MagicMock()
    skill_stager = MagicMock()
    plugin_stager = MagicMock()
    attachment_stager = MagicMock()
    claude_md_stager = MagicMock()
    slash_command_stager = MagicMock()
    subagent_stager = MagicMock()

    with patch(
        "app.services.run_dispatch_service.get_settings",
        side_effect=AssertionError("settings should be injected"),
    ):
        service = RunDispatchService.create_default(
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
        )

    assert service.settings is settings


def test_create_default_accepts_lazy_container_pool_factory() -> None:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )
    container_pool = MagicMock()
    container_pool_factory = MagicMock(return_value=container_pool)

    with patch(
        "app.services.run_dispatch_service.TaskDispatcher.get_container_pool",
        side_effect=AssertionError("default container pool should be injected"),
    ):
        service = RunDispatchService.create_default(
            settings=settings,
            container_pool_factory=container_pool_factory,
        )

        container_pool_factory.assert_not_called()
        assert service.container_pool is container_pool

    container_pool_factory.assert_called_once_with()


def test_create_default_accepts_lazy_runtime_factory() -> None:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )
    runtime = MagicMock()
    runtime_factory = MagicMock(return_value=runtime)

    with patch(
        "app.services.run_dispatch_service.TaskDispatcher.get_container_pool",
        side_effect=AssertionError("default container pool should stay lazy"),
    ):
        service = RunDispatchService.create_default(
            settings=settings,
            runtime_factory=runtime_factory,
        )

        runtime_factory.assert_not_called()
        assert service.runtime is runtime

    runtime_factory.assert_called_once_with()


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
