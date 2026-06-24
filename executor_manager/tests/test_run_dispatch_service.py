from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch
import typing

import pytest

from app.services.run_dispatch_claim import RunDispatchClaim
from app.services.run_dispatch_execution_context import RunDispatchExecutionContext
from app.services.run_dispatch_runtime import RunDispatchRuntimeAllocation
from app.services.run_dispatch_service import RunDispatchService


def _make_claim(
    *,
    run_id: str = "run-123",
    session_id: str = "sess-123",
    user_id: str = "user-123",
    prompt: str = "do work",
    config_snapshot: dict | None = None,
    sdk_session_id: str | None = None,
    permission_mode: str = "default",
) -> RunDispatchClaim:
    return RunDispatchClaim(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        prompt=prompt,
        config_snapshot=config_snapshot or {},
        sdk_session_id=sdk_session_id,
        permission_mode=permission_mode,
    )


def _make_dispatch_service(
    *,
    runtime: object | None = None,
    computer_provider: object | None = None,
    config_preparer: object | None = None,
    state_gateway: object | None = None,
    executor_gateway: object | None = None,
    execution_context_provider: object | None = None,
) -> RunDispatchService:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
        task_timeout_seconds=3600,
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

    kwargs = {
        "settings": settings,
        "backend_client": backend_client,
        "executor_client": executor_client,
        "config_resolver": config_resolver,
        "skill_stager": skill_stager,
        "plugin_stager": plugin_stager,
        "attachment_stager": attachment_stager,
        "claude_md_stager": claude_md_stager,
        "slash_command_stager": slash_command_stager,
        "subagent_stager": subagent_stager,
        "container_pool": container_pool,
        "runtime": runtime,
        "computer_provider": computer_provider,
        "config_preparer": config_preparer,
    }
    if state_gateway is not None:
        kwargs["state_gateway"] = state_gateway
    if executor_gateway is not None:
        kwargs["executor_gateway"] = executor_gateway
    if execution_context_provider is not None:
        kwargs["execution_context_provider"] = execution_context_provider
    return RunDispatchService(**kwargs)


@pytest.mark.asyncio
async def test_dispatch_claim_delegates_runtime_allocation_to_injected_runtime() -> (
    None
):
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=RunDispatchRuntimeAllocation(
            executor_url="http://runtime-executor.local",
            container_id="runtime-container-1",
        )
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
    claim = _make_claim(
        config_snapshot={
            "container_mode": "persistent",
            "container_id": "existing-container",
            "browser_enabled": True,
        },
    )

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
        return_value=RunDispatchRuntimeAllocation(
            executor_url="http://runtime-executor.local",
            container_id="runtime-container-1",
        )
    )
    runtime.cancel_runtime = AsyncMock()
    service = _make_dispatch_service(runtime=runtime)
    service.backend_client.start_run.side_effect = RuntimeError("start failed")
    service.container_pool.cancel_task.side_effect = AssertionError(
        "runtime port should own cancellation"
    )
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    runtime.cancel_runtime.assert_awaited_once_with("sess-123")


@pytest.mark.asyncio
async def test_dispatch_claim_delegates_config_preparation_to_injected_port() -> None:
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=RunDispatchRuntimeAllocation(
            executor_url="http://runtime-executor.local",
            container_id="runtime-container-1",
        )
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
    claim = _make_claim(config_snapshot={"container_mode": "persistent"})

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


@pytest.mark.asyncio
async def test_dispatch_claim_delegates_run_state_to_injected_gateway() -> None:
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=RunDispatchRuntimeAllocation(
            executor_url="http://runtime-executor.local",
            container_id="runtime-container-1",
        )
    )
    runtime.cancel_runtime = AsyncMock()
    config_preparer = MagicMock()
    config_preparer.prepare_config = AsyncMock(
        return_value={
            "skill_files": {},
            "plugin_files": {},
            "input_files": [],
            "mcp_config": {"server-a": {}, "server-b": {}},
        }
    )
    state_gateway = MagicMock()
    state_gateway.record_mcp_staged_servers = AsyncMock()
    state_gateway.start_run = AsyncMock()
    state_gateway.fail_run = AsyncMock()
    service = _make_dispatch_service(
        runtime=runtime,
        config_preparer=config_preparer,
        state_gateway=state_gateway,
    )
    service.backend_client.record_mcp_transition.side_effect = AssertionError(
        "MCP state should stay behind state gateway"
    )
    service.backend_client.start_run.side_effect = AssertionError(
        "run start should stay behind state gateway"
    )
    service.backend_client.fail_run.side_effect = AssertionError(
        "run failure should stay behind state gateway"
    )
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    state_gateway.record_mcp_staged_servers.assert_awaited_once_with(
        run_id="run-123",
        session_id="sess-123",
        server_names=["server-a", "server-b"],
    )
    state_gateway.start_run.assert_awaited_once_with(
        run_id="run-123",
        worker_id="worker-1",
        lease_seconds=3600,
    )
    state_gateway.fail_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_claim_does_not_call_per_server_mcp_staged() -> None:
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=RunDispatchRuntimeAllocation(
            executor_url="http://runtime-executor.local",
            container_id="runtime-container-1",
        )
    )
    runtime.cancel_runtime = AsyncMock()
    config_preparer = MagicMock()
    config_preparer.prepare_config = AsyncMock(
        return_value={
            "skill_files": {},
            "plugin_files": {},
            "input_files": [],
            "mcp_config": {"server-a": {}, "server-b": {}},
        }
    )
    state_gateway = MagicMock()
    state_gateway.record_mcp_staged_servers = AsyncMock()
    state_gateway.record_mcp_staged = AsyncMock(
        side_effect=AssertionError("should use batch method")
    )
    state_gateway.start_run = AsyncMock()
    state_gateway.fail_run = AsyncMock()
    service = _make_dispatch_service(
        runtime=runtime,
        config_preparer=config_preparer,
        state_gateway=state_gateway,
    )
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    state_gateway.record_mcp_staged_servers.assert_awaited_once_with(
        run_id="run-123",
        session_id="sess-123",
        server_names=["server-a", "server-b"],
    )
    state_gateway.record_mcp_staged.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_claim_delegates_executor_call_to_injected_gateway() -> None:
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        return_value=RunDispatchRuntimeAllocation(
            executor_url="http://runtime-executor.local",
            container_id="runtime-container-1",
        )
    )
    runtime.cancel_runtime = AsyncMock()
    config_preparer = MagicMock()
    config_preparer.prepare_config = AsyncMock(
        return_value={
            "skill_files": {},
            "plugin_files": {},
            "input_files": [],
        }
    )
    state_gateway = MagicMock()
    state_gateway.record_mcp_staged = AsyncMock()
    state_gateway.start_run = AsyncMock()
    state_gateway.fail_run = AsyncMock()
    executor_gateway = MagicMock()
    executor_gateway.execute_run = AsyncMock()
    service = _make_dispatch_service(
        runtime=runtime,
        config_preparer=config_preparer,
        state_gateway=state_gateway,
        executor_gateway=executor_gateway,
    )
    service.executor_client.execute_task.side_effect = AssertionError(
        "executor client should stay behind executor gateway"
    )
    claim = _make_claim(sdk_session_id="sdk-123", permission_mode="acceptEdits")

    await service.dispatch_claim(claim, worker_id="worker-1")

    executor_gateway.execute_run.assert_awaited_once_with(
        executor_url="http://runtime-executor.local",
        session_id="sess-123",
        run_id="run-123",
        prompt="do work",
        execution_context=RunDispatchExecutionContext(
            callback_base_url="http://manager.local",
            callback_url="http://manager.local/api/v1/callback",
            callback_token="callback-token",
            task_lease_secret="lease-secret",
            running_lease_seconds=3600,
        ),
        config={
            "skill_files": {},
            "plugin_files": {},
            "input_files": [],
        },
        sdk_session_id="sdk-123",
        permission_mode="acceptEdits",
    )


@pytest.mark.asyncio
async def test_dispatch_claim_accepts_parsed_claim_command() -> None:
    service = _make_dispatch_service()
    claim = RunDispatchClaim(
        run_id="run-123",
        session_id="sess-123",
        user_id="user-123",
        prompt="do work",
        config_snapshot={},
        sdk_session_id="sdk-123",
        permission_mode="acceptEdits",
    )

    await service.dispatch_claim(claim, worker_id="worker-1")

    service.executor_client.execute_task.assert_awaited_once()
    call_kwargs = service.executor_client.execute_task.call_args.kwargs
    assert call_kwargs["run_id"] == "run-123"
    assert call_kwargs["sdk_session_id"] == "sdk-123"
    assert call_kwargs["permission_mode"] == "acceptEdits"


@pytest.mark.asyncio
async def test_dispatch_claim_uses_injected_execution_context_provider() -> None:
    execution_context_provider = MagicMock()
    execution_context_provider.get_context = MagicMock(
        return_value=RunDispatchExecutionContext(
            callback_base_url="http://provider.local",
            callback_url="http://provider.local/callback",
            callback_token="provider-token",
            task_lease_secret="provider-lease-secret",
            running_lease_seconds=5400,
        )
    )
    service = _make_dispatch_service(
        execution_context_provider=execution_context_provider
    )
    service.settings.callback_base_url = ""
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    execution_context_provider.get_context.assert_called_once_with()
    call_kwargs = service.executor_client.execute_task.call_args.kwargs
    assert call_kwargs["callback_url"] == "http://provider.local/callback"
    assert call_kwargs["callback_token"] == "provider-token"
    assert call_kwargs["task_lease_secret"] == "provider-lease-secret"
    assert call_kwargs["callback_base_url"] == "http://provider.local"


@pytest.mark.asyncio
async def test_dispatch_claim_uses_running_lease_from_execution_context() -> None:
    execution_context_provider = MagicMock()
    execution_context_provider.get_context = MagicMock(
        return_value=RunDispatchExecutionContext(
            callback_base_url="http://provider.local",
            callback_url="http://provider.local/callback",
            callback_token="provider-token",
            task_lease_secret="provider-lease-secret",
            running_lease_seconds=5400,
        )
    )
    state_gateway = MagicMock()
    state_gateway.record_mcp_staged_servers = AsyncMock()
    state_gateway.start_run = AsyncMock()
    state_gateway.fail_run = AsyncMock()
    service = _make_dispatch_service(
        execution_context_provider=execution_context_provider,
        state_gateway=state_gateway,
    )
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    state_gateway.start_run.assert_awaited_once_with(
        run_id="run-123",
        worker_id="worker-1",
        lease_seconds=5400,
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
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    service.executor_client.execute_task.assert_not_awaited()
    service.backend_client.fail_run.assert_awaited_once()
    fail_kwargs = service.backend_client.fail_run.call_args.kwargs
    assert fail_kwargs["run_id"] == "run-123"
    assert fail_kwargs["worker_id"] == "worker-1"
    assert "start failed" in fail_kwargs["error_message"]
    service.container_pool.cancel_task.assert_awaited_once_with("sess-123")


@pytest.mark.asyncio
async def test_dispatch_claim_does_not_cancel_runtime_when_prepare_config_fails() -> (
    None
):
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock()
    runtime.cancel_runtime = AsyncMock()
    config_preparer = MagicMock()
    config_preparer.prepare_config = AsyncMock(side_effect=RuntimeError("prep failed"))
    state_gateway = MagicMock()
    state_gateway.fail_run = AsyncMock()
    service = _make_dispatch_service(
        runtime=runtime,
        config_preparer=config_preparer,
        state_gateway=state_gateway,
    )
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    runtime.allocate_runtime.assert_not_awaited()
    runtime.cancel_runtime.assert_not_awaited()
    state_gateway.fail_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_claim_starts_run_before_executor_execute_task() -> None:
    service = _make_dispatch_service()
    call_order: list[str] = []

    async def start_run(
        *, run_id: str, worker_id: str, lease_seconds: int | None = None
    ) -> None:
        call_order.append(f"start:{run_id}:{worker_id}")

    async def execute_task(**kwargs) -> str:
        call_order.append(f"execute:{kwargs['run_id']}")
        return "sess-123"

    service.backend_client.start_run.side_effect = start_run
    service.executor_client.execute_task.side_effect = execute_task
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    assert call_order == ["start:run-123:worker-1", "execute:run-123"]


@pytest.mark.asyncio
async def test_dispatch_claim_passes_dedicated_task_lease_secret() -> None:
    service = _make_dispatch_service()
    claim = _make_claim()

    await service.dispatch_claim(claim, worker_id="worker-1")

    service.executor_client.execute_task.assert_awaited_once()
    call_kwargs = service.executor_client.execute_task.call_args.kwargs
    assert call_kwargs["callback_token"] == "callback-token"
    assert call_kwargs["task_lease_secret"] == "lease-secret"


def test_constructor_uses_port_types_not_any() -> None:
    """Assert RunDispatchService constructor annotations use Port protocol names."""
    sig = typing.get_type_hints(RunDispatchService.__init__)

    port_params = [
        "backend_client",
        "executor_client",
        "config_resolver",
        "skill_stager",
        "plugin_stager",
        "attachment_stager",
        "claude_md_stager",
        "slash_command_stager",
        "subagent_stager",
    ]

    for param in port_params:
        annotation = sig.get(param)
        assert annotation is not None, f"{param} should have annotation"
        annotation_str = str(annotation)
        assert "Any" not in annotation_str, f"{param} should not use Any"
        assert "Port" in annotation_str, f"{param} should use Port protocol name"


def test_constructor_factory_uses_port_types_not_any() -> None:
    """Assert RunDispatchService constructor factory annotations use Port protocol names."""
    sig = typing.get_type_hints(RunDispatchService.__init__)

    factory_params = [
        ("backend_client_factory", "RunDispatchBackendClientPort"),
        ("executor_client_factory", "RunDispatchExecutorClientPort"),
    ]

    for param, port_name in factory_params:
        annotation = sig.get(param)
        assert annotation is not None, f"{param} should have annotation"
        annotation_str = str(annotation)
        assert "Any" not in annotation_str, f"{param} should not use Any"
        assert port_name in annotation_str, f"{param} should use {port_name}"


def test_create_default_uses_port_types_not_any() -> None:
    """Assert create_default parameter annotations use Port protocol names."""
    sig = typing.get_type_hints(RunDispatchService.create_default)

    port_params = [
        "backend_client",
        "executor_client",
        "config_resolver",
        "skill_stager",
        "plugin_stager",
        "attachment_stager",
        "claude_md_stager",
        "slash_command_stager",
        "subagent_stager",
    ]

    for param in port_params:
        annotation = sig.get(param)
        assert annotation is not None, f"{param} should have annotation"
        annotation_str = str(annotation)
        assert "Any" not in annotation_str, f"{param} should not use Any"
        assert "Port" in annotation_str, f"{param} should use Port protocol name"


def test_create_default_factory_uses_port_types_not_any() -> None:
    """Assert create_default factory parameter annotations use Port protocol names."""
    sig = typing.get_type_hints(RunDispatchService.create_default)

    factory_params = [
        ("backend_client_factory", "RunDispatchBackendClientPort"),
        ("executor_client_factory", "RunDispatchExecutorClientPort"),
    ]

    for param, port_name in factory_params:
        annotation = sig.get(param)
        assert annotation is not None, f"{param} should have annotation"
        annotation_str = str(annotation)
        assert "Any" not in annotation_str, f"{param} should not use Any"
        assert port_name in annotation_str, f"{param} should use {port_name}"


def test_config_resolver_factory_uses_config_resolver_settings_not_any() -> None:
    """Assert config_resolver_factory settings parameter uses ConfigResolverSettings."""
    init_sig = typing.get_type_hints(RunDispatchService.__init__)
    create_default_sig = typing.get_type_hints(RunDispatchService.create_default)

    for sig, method_name in [
        (init_sig, "__init__"),
        (create_default_sig, "create_default"),
    ]:
        annotation = sig.get("config_resolver_factory")
        assert annotation is not None, (
            f"{method_name} config_resolver_factory should have annotation"
        )
        annotation_str = str(annotation)
        assert "Any" not in annotation_str, (
            f"{method_name} config_resolver_factory should not use Any for settings"
        )
        assert "ConfigResolverSettings" in annotation_str, (
            f"{method_name} config_resolver_factory should use ConfigResolverSettings"
        )


def test_init_settings_uses_named_protocol_not_any() -> None:
    """Assert __init__ settings parameter uses RunDispatchServiceSettings, not Any."""
    sig = typing.get_type_hints(RunDispatchService.__init__)

    annotation = sig.get("settings")
    assert annotation is not None, "__init__ settings should have annotation"
    annotation_str = str(annotation)
    assert "Any" not in annotation_str, (
        "__init__ settings should not use Any annotation"
    )
    assert "RunDispatchServiceSettings" in annotation_str, (
        "__init__ settings should use RunDispatchServiceSettings protocol"
    )


def test_create_default_settings_uses_named_protocol_not_any() -> None:
    """Assert create_default settings parameter uses RunDispatchServiceSettings, not Any."""
    sig = typing.get_type_hints(RunDispatchService.create_default)

    annotation = sig.get("settings")
    assert annotation is not None, "create_default settings should have annotation"
    annotation_str = str(annotation)
    assert "Any" not in annotation_str, (
        "create_default settings should not use Any annotation"
    )
    assert "RunDispatchServiceSettings" in annotation_str, (
        "create_default settings should use RunDispatchServiceSettings protocol"
    )


def test_dispatch_claim_parameter_uses_run_dispatch_claim_not_raw_types() -> None:
    """Assert dispatch_claim claim parameter uses RunDispatchClaim, not Any/Mapping/dict."""
    sig = typing.get_type_hints(RunDispatchService.dispatch_claim)

    annotation = sig.get("claim")
    assert annotation is not None, "dispatch_claim claim should have annotation"
    annotation_str = str(annotation)
    assert "Any" not in annotation_str, (
        "dispatch_claim claim should not use Any annotation"
    )
    assert "Mapping" not in annotation_str, (
        "dispatch_claim claim should not use Mapping annotation"
    )
    assert "dict" not in annotation_str, (
        "dispatch_claim claim should not use dict annotation"
    )
    assert "RunDispatchClaim" in annotation_str, (
        "dispatch_claim claim should use RunDispatchClaim"
    )


@pytest.mark.asyncio
async def test_dispatch_claim_rejects_raw_mapping_payload_before_ports_called() -> None:
    """Assert raw mapping payloads raise TypeError before any ports are called."""
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        side_effect=AssertionError("runtime should not be called for raw payload")
    )
    config_preparer = MagicMock()
    config_preparer.prepare_config = AsyncMock(
        side_effect=AssertionError(
            "config_preparer should not be called for raw payload"
        )
    )
    state_gateway = MagicMock()
    state_gateway.start_run = AsyncMock(
        side_effect=AssertionError("state_gateway should not be called for raw payload")
    )
    executor_gateway = MagicMock()
    executor_gateway.execute_run = AsyncMock(
        side_effect=AssertionError(
            "executor_gateway should not be called for raw payload"
        )
    )
    service = _make_dispatch_service(
        runtime=runtime,
        config_preparer=config_preparer,
        state_gateway=state_gateway,
        executor_gateway=executor_gateway,
    )
    raw_payload = {
        "run": {"run_id": "run-123", "session_id": "sess-123"},
        "user_id": "user-123",
        "prompt": "do work",
        "config_snapshot": {},
    }

    with pytest.raises(TypeError, match="RunDispatchClaim"):
        await service.dispatch_claim(raw_payload, worker_id="worker-1")  # type: ignore[arg-type]

    runtime.allocate_runtime.assert_not_awaited()
    config_preparer.prepare_config.assert_not_awaited()
    state_gateway.start_run.assert_not_awaited()
    executor_gateway.execute_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_claim_rejects_dict_payload_with_type_error() -> None:
    """Assert dict payloads raise TypeError, not other exceptions."""
    service = _make_dispatch_service()
    raw_payload = {"run": {"run_id": "run-123"}, "user_id": "user-123"}

    with pytest.raises(TypeError, match="dispatch_claim requires RunDispatchClaim"):
        await service.dispatch_claim(raw_payload, worker_id="worker-1")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dispatch_claim_uses_computer_provider_when_injected() -> None:
    """When computer_provider is injected, dispatch goes through acquire/release."""
    from app.services.computer_provider import (
        ComputerCapability,
        ComputerInstance,
    )

    provider = MagicMock()
    provider.acquire = AsyncMock(
        return_value=ComputerInstance(
            instance_id="docker-123",
            executor_endpoint="http://provider-executor.local",
            provider="docker",
            capabilities={
                ComputerCapability.SHELL,
                ComputerCapability.FILESYSTEM,
                ComputerCapability.BROWSER,
            },
        )
    )
    provider.release = AsyncMock()

    # runtime must NOT be called when computer_provider is set
    runtime = MagicMock()
    runtime.allocate_runtime = AsyncMock(
        side_effect=AssertionError("runtime should stay behind computer_provider")
    )
    runtime.cancel_runtime = AsyncMock(
        side_effect=AssertionError("runtime cancel should stay behind computer_provider")
    )

    service = _make_dispatch_service(runtime=runtime, computer_provider=provider)
    service.config_resolver.resolve.return_value = {
        "skill_files": {},
        "plugin_files": {},
        "input_files": [],
        "browser_enabled": True,
    }

    claim = _make_claim(
        config_snapshot={
            "container_mode": "ephemeral",
            "container_id": "reuse-id-1",
            "browser_enabled": True,
        },
    )

    await service.dispatch_claim(claim, worker_id="worker-1")

    # acquire called with correct capability translation
    provider.acquire.assert_awaited_once()
    call_kwargs = provider.acquire.await_args.kwargs
    assert call_kwargs["session_id"] == "sess-123"
    assert call_kwargs["user_id"] == "user-123"
    assert ComputerCapability.BROWSER in call_kwargs["requires"]
    assert ComputerCapability.SHELL in call_kwargs["requires"]
    assert call_kwargs["reuse_id"] == "reuse-id-1"

    # executor received the provider's endpoint
    service.executor_client.execute_task.assert_awaited_once()
    assert (
        service.executor_client.execute_task.call_args.kwargs["executor_url"]
        == "http://provider-executor.local"
    )

    # release not called on success
    provider.release.assert_not_awaited()
