import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

from app.core.settings import get_settings
from app.scheduler.task_dispatcher import TaskDispatcher
from app.services.attachment_stager import AttachmentStager
from app.services.backend_client import BackendClient
from app.services.claude_md_stager import ClaudeMdStager
from app.services.config_resolver import ConfigResolver
from app.services.executor_client import ExecutorClient
from app.services.plugin_stager import PluginStager
from app.services.run_dispatch_claim import RunDispatchClaim
from app.services.run_dispatch_config_preparer import (
    RunDispatchConfigPreparer,
    StagingRunDispatchConfigPreparer,
)
from app.services.run_dispatch_executor_gateway import (
    ExecutorClientRunDispatchGateway,
    RunDispatchExecutorGateway,
)
from app.services.run_dispatch_execution_context import (
    RunDispatchExecutionContextProvider,
    SettingsRunDispatchExecutionContextProvider,
)
from app.services.run_dispatch_runtime import (
    ContainerPoolRunDispatchRuntime,
    RunDispatchRuntime,
)
from app.services.run_dispatch_state_gateway import (
    BackendRunDispatchStateGateway,
    RunDispatchStateGateway,
)
from app.services.skill_stager import SkillStager
from app.services.slash_command_stager import SlashCommandStager
from app.services.sub_agent_stager import SubAgentStager

logger = logging.getLogger(__name__)


def build_run_dispatch_backend_client() -> BackendClient:
    return BackendClient()


def build_run_dispatch_executor_client() -> ExecutorClient:
    return ExecutorClient()


def build_run_dispatch_config_resolver(
    backend_client: Any, settings: Any
) -> ConfigResolver:
    return ConfigResolver(backend_client, settings=settings)


def build_run_dispatch_skill_stager() -> SkillStager:
    return SkillStager()


def build_run_dispatch_plugin_stager() -> PluginStager:
    return PluginStager()


def build_run_dispatch_attachment_stager() -> AttachmentStager:
    return AttachmentStager()


def build_run_dispatch_claude_md_stager() -> ClaudeMdStager:
    return ClaudeMdStager()


def build_run_dispatch_slash_command_stager() -> SlashCommandStager:
    return SlashCommandStager()


def build_run_dispatch_subagent_stager() -> SubAgentStager:
    return SubAgentStager()


def build_run_dispatch_container_pool() -> Any:
    return TaskDispatcher.get_container_pool()


class RunDispatchService:
    """Dispatch claimed runs to executor runtimes."""

    def __init__(
        self,
        *,
        settings: Any,
        backend_client: Any | None = None,
        executor_client: Any | None = None,
        config_resolver: Any | None = None,
        skill_stager: Any | None = None,
        plugin_stager: Any | None = None,
        attachment_stager: Any | None = None,
        claude_md_stager: Any | None = None,
        slash_command_stager: Any | None = None,
        subagent_stager: Any | None = None,
        container_pool: Any | None = None,
        runtime: RunDispatchRuntime | None = None,
        config_preparer: RunDispatchConfigPreparer | None = None,
        state_gateway: RunDispatchStateGateway | None = None,
        executor_gateway: RunDispatchExecutorGateway | None = None,
        execution_context_provider: RunDispatchExecutionContextProvider | None = None,
        backend_client_factory: Callable[[], Any] | None = None,
        executor_client_factory: Callable[[], Any] | None = None,
        config_resolver_factory: Callable[[Any, Any], Any] | None = None,
        skill_stager_factory: Callable[[], Any] | None = None,
        plugin_stager_factory: Callable[[], Any] | None = None,
        attachment_stager_factory: Callable[[], Any] | None = None,
        claude_md_stager_factory: Callable[[], Any] | None = None,
        slash_command_stager_factory: Callable[[], Any] | None = None,
        subagent_stager_factory: Callable[[], Any] | None = None,
        container_pool_factory: Callable[[], Any] | None = None,
        runtime_factory: Callable[[], RunDispatchRuntime] | None = None,
        config_preparer_factory: Callable[[], RunDispatchConfigPreparer] | None = None,
        state_gateway_factory: Callable[[], RunDispatchStateGateway] | None = None,
        executor_gateway_factory: Callable[[], RunDispatchExecutorGateway]
        | None = None,
        execution_context_provider_factory: Callable[
            [], RunDispatchExecutionContextProvider
        ]
        | None = None,
    ) -> None:
        self.settings = settings
        self._backend_client = backend_client
        self._backend_client_factory = (
            backend_client_factory or build_run_dispatch_backend_client
        )
        self._executor_client = executor_client
        self._executor_client_factory = (
            executor_client_factory or build_run_dispatch_executor_client
        )
        self._container_pool = container_pool
        self._container_pool_factory = (
            container_pool_factory or build_run_dispatch_container_pool
        )
        self._runtime = runtime
        self._runtime_factory = runtime_factory
        self._config_preparer = config_preparer
        self._config_preparer_factory = config_preparer_factory
        self._state_gateway = state_gateway
        self._state_gateway_factory = state_gateway_factory
        self._executor_gateway = executor_gateway
        self._executor_gateway_factory = executor_gateway_factory
        self._execution_context_provider = execution_context_provider
        self._execution_context_provider_factory = execution_context_provider_factory
        self._config_resolver = config_resolver
        self._config_resolver_factory = (
            config_resolver_factory or build_run_dispatch_config_resolver
        )
        self._skill_stager = skill_stager
        self._skill_stager_factory = (
            skill_stager_factory or build_run_dispatch_skill_stager
        )
        self._plugin_stager = plugin_stager
        self._plugin_stager_factory = (
            plugin_stager_factory or build_run_dispatch_plugin_stager
        )
        self._attachment_stager = attachment_stager
        self._attachment_stager_factory = (
            attachment_stager_factory or build_run_dispatch_attachment_stager
        )
        self._claude_md_stager = claude_md_stager
        self._claude_md_stager_factory = (
            claude_md_stager_factory or build_run_dispatch_claude_md_stager
        )
        self._slash_command_stager = slash_command_stager
        self._slash_command_stager_factory = (
            slash_command_stager_factory or build_run_dispatch_slash_command_stager
        )
        self._subagent_stager = subagent_stager
        self._subagent_stager_factory = (
            subagent_stager_factory or build_run_dispatch_subagent_stager
        )

    @property
    def backend_client(self) -> Any:
        if self._backend_client is None:
            self._backend_client = self._backend_client_factory()
        return self._backend_client

    @backend_client.setter
    def backend_client(self, value: Any) -> None:
        self._backend_client = value

    @property
    def executor_client(self) -> Any:
        if self._executor_client is None:
            self._executor_client = self._executor_client_factory()
        return self._executor_client

    @executor_client.setter
    def executor_client(self, value: Any) -> None:
        self._executor_client = value

    @property
    def container_pool(self) -> Any:
        if self._container_pool is None:
            self._container_pool = self._container_pool_factory()
        return self._container_pool

    @container_pool.setter
    def container_pool(self, value: Any) -> None:
        self._container_pool = value

    @property
    def runtime(self) -> RunDispatchRuntime:
        if self._runtime is None:
            self._runtime = (
                self._runtime_factory()
                if self._runtime_factory is not None
                else ContainerPoolRunDispatchRuntime(self.container_pool)
            )
        return self._runtime

    @runtime.setter
    def runtime(self, value: RunDispatchRuntime) -> None:
        self._runtime = value

    @property
    def config_preparer(self) -> RunDispatchConfigPreparer:
        if self._config_preparer is None and self._config_preparer_factory is not None:
            self._config_preparer = self._config_preparer_factory()
        if self._config_preparer is None:
            self._config_preparer = StagingRunDispatchConfigPreparer(
                backend_client=self.backend_client,
                config_resolver=self.config_resolver,
                skill_stager=self.skill_stager,
                plugin_stager=self.plugin_stager,
                attachment_stager=self.attachment_stager,
                claude_md_stager=self.claude_md_stager,
                slash_command_stager=self.slash_command_stager,
                subagent_stager=self.subagent_stager,
            )
        return self._config_preparer

    @config_preparer.setter
    def config_preparer(self, value: RunDispatchConfigPreparer) -> None:
        self._config_preparer = value

    @property
    def state_gateway(self) -> RunDispatchStateGateway:
        if self._state_gateway is None and self._state_gateway_factory is not None:
            self._state_gateway = self._state_gateway_factory()
        if self._state_gateway is None:
            self._state_gateway = BackendRunDispatchStateGateway(self.backend_client)
        return self._state_gateway

    @state_gateway.setter
    def state_gateway(self, value: RunDispatchStateGateway) -> None:
        self._state_gateway = value

    @property
    def executor_gateway(self) -> RunDispatchExecutorGateway:
        if (
            self._executor_gateway is None
            and self._executor_gateway_factory is not None
        ):
            self._executor_gateway = self._executor_gateway_factory()
        if self._executor_gateway is None:
            self._executor_gateway = ExecutorClientRunDispatchGateway(
                self.executor_client
            )
        return self._executor_gateway

    @executor_gateway.setter
    def executor_gateway(self, value: RunDispatchExecutorGateway) -> None:
        self._executor_gateway = value

    @property
    def execution_context_provider(self) -> RunDispatchExecutionContextProvider:
        if (
            self._execution_context_provider is None
            and self._execution_context_provider_factory is not None
        ):
            self._execution_context_provider = (
                self._execution_context_provider_factory()
            )
        if self._execution_context_provider is None:
            self._execution_context_provider = (
                SettingsRunDispatchExecutionContextProvider(self.settings)
            )
        return self._execution_context_provider

    @execution_context_provider.setter
    def execution_context_provider(
        self,
        value: RunDispatchExecutionContextProvider,
    ) -> None:
        self._execution_context_provider = value

    @property
    def config_resolver(self) -> Any:
        if self._config_resolver is None:
            self._config_resolver = self._config_resolver_factory(
                self.backend_client,
                self.settings,
            )
        return self._config_resolver

    @config_resolver.setter
    def config_resolver(self, value: Any) -> None:
        self._config_resolver = value

    @property
    def skill_stager(self) -> Any:
        if self._skill_stager is None:
            self._skill_stager = self._skill_stager_factory()
        return self._skill_stager

    @skill_stager.setter
    def skill_stager(self, value: Any) -> None:
        self._skill_stager = value

    @property
    def plugin_stager(self) -> Any:
        if self._plugin_stager is None:
            self._plugin_stager = self._plugin_stager_factory()
        return self._plugin_stager

    @plugin_stager.setter
    def plugin_stager(self, value: Any) -> None:
        self._plugin_stager = value

    @property
    def attachment_stager(self) -> Any:
        if self._attachment_stager is None:
            self._attachment_stager = self._attachment_stager_factory()
        return self._attachment_stager

    @attachment_stager.setter
    def attachment_stager(self, value: Any) -> None:
        self._attachment_stager = value

    @property
    def claude_md_stager(self) -> Any:
        if self._claude_md_stager is None:
            self._claude_md_stager = self._claude_md_stager_factory()
        return self._claude_md_stager

    @claude_md_stager.setter
    def claude_md_stager(self, value: Any) -> None:
        self._claude_md_stager = value

    @property
    def slash_command_stager(self) -> Any:
        if self._slash_command_stager is None:
            self._slash_command_stager = self._slash_command_stager_factory()
        return self._slash_command_stager

    @slash_command_stager.setter
    def slash_command_stager(self, value: Any) -> None:
        self._slash_command_stager = value

    @property
    def subagent_stager(self) -> Any:
        if self._subagent_stager is None:
            self._subagent_stager = self._subagent_stager_factory()
        return self._subagent_stager

    @subagent_stager.setter
    def subagent_stager(self, value: Any) -> None:
        self._subagent_stager = value

    @classmethod
    def create_default(
        cls,
        *,
        settings: Any | None = None,
        backend_client: Any | None = None,
        executor_client: Any | None = None,
        container_pool: Any | None = None,
        config_resolver: Any | None = None,
        skill_stager: Any | None = None,
        plugin_stager: Any | None = None,
        attachment_stager: Any | None = None,
        claude_md_stager: Any | None = None,
        slash_command_stager: Any | None = None,
        subagent_stager: Any | None = None,
        runtime: RunDispatchRuntime | None = None,
        config_preparer: RunDispatchConfigPreparer | None = None,
        state_gateway: RunDispatchStateGateway | None = None,
        executor_gateway: RunDispatchExecutorGateway | None = None,
        execution_context_provider: RunDispatchExecutionContextProvider | None = None,
        backend_client_factory: Callable[[], Any] | None = None,
        executor_client_factory: Callable[[], Any] | None = None,
        config_resolver_factory: Callable[[Any, Any], Any] | None = None,
        skill_stager_factory: Callable[[], Any] | None = None,
        plugin_stager_factory: Callable[[], Any] | None = None,
        attachment_stager_factory: Callable[[], Any] | None = None,
        claude_md_stager_factory: Callable[[], Any] | None = None,
        slash_command_stager_factory: Callable[[], Any] | None = None,
        subagent_stager_factory: Callable[[], Any] | None = None,
        container_pool_factory: Callable[[], Any] | None = None,
        runtime_factory: Callable[[], RunDispatchRuntime] | None = None,
        config_preparer_factory: Callable[[], RunDispatchConfigPreparer] | None = None,
        state_gateway_factory: Callable[[], RunDispatchStateGateway] | None = None,
        executor_gateway_factory: Callable[[], RunDispatchExecutorGateway]
        | None = None,
        execution_context_provider_factory: Callable[
            [], RunDispatchExecutionContextProvider
        ]
        | None = None,
    ) -> "RunDispatchService":
        settings = settings if settings is not None else get_settings()
        backend_factory = backend_client_factory or build_run_dispatch_backend_client
        executor_factory = executor_client_factory or build_run_dispatch_executor_client
        config_factory = config_resolver_factory or build_run_dispatch_config_resolver
        skill_factory = skill_stager_factory or build_run_dispatch_skill_stager
        plugin_factory = plugin_stager_factory or build_run_dispatch_plugin_stager
        attachment_factory = (
            attachment_stager_factory or build_run_dispatch_attachment_stager
        )
        claude_md_factory = (
            claude_md_stager_factory or build_run_dispatch_claude_md_stager
        )
        slash_command_factory = (
            slash_command_stager_factory or build_run_dispatch_slash_command_stager
        )
        subagent_factory = subagent_stager_factory or build_run_dispatch_subagent_stager
        container_factory = container_pool_factory or build_run_dispatch_container_pool
        return cls(
            settings=settings,
            backend_client=backend_client,
            backend_client_factory=backend_factory,
            executor_client=executor_client,
            executor_client_factory=executor_factory,
            container_pool=container_pool,
            container_pool_factory=container_factory,
            runtime=runtime,
            runtime_factory=runtime_factory,
            config_preparer=config_preparer,
            config_preparer_factory=config_preparer_factory,
            state_gateway=state_gateway,
            state_gateway_factory=state_gateway_factory,
            executor_gateway=executor_gateway,
            executor_gateway_factory=executor_gateway_factory,
            execution_context_provider=execution_context_provider,
            execution_context_provider_factory=execution_context_provider_factory,
            config_resolver=config_resolver,
            config_resolver_factory=config_factory,
            skill_stager=skill_stager,
            skill_stager_factory=skill_factory,
            plugin_stager=plugin_stager,
            plugin_stager_factory=plugin_factory,
            attachment_stager=attachment_stager,
            attachment_stager_factory=attachment_factory,
            claude_md_stager=claude_md_stager,
            claude_md_stager_factory=claude_md_factory,
            slash_command_stager=slash_command_stager,
            slash_command_stager_factory=slash_command_factory,
            subagent_stager=subagent_stager,
            subagent_stager_factory=subagent_factory,
        )

    async def dispatch_claim(
        self,
        claim: RunDispatchClaim | Mapping[str, Any],
        *,
        worker_id: str,
    ) -> None:
        dispatch_started = time.perf_counter()
        dispatch_claim = (
            claim
            if isinstance(claim, RunDispatchClaim)
            else RunDispatchClaim.from_payload(claim)
        )
        if dispatch_claim is None:
            logger.error(f"Invalid claim payload: {claim}")
            return

        run_id = dispatch_claim.run_id
        run_id_str = dispatch_claim.run_id_str
        session_id = dispatch_claim.session_id
        user_id = dispatch_claim.user_id
        prompt = dispatch_claim.prompt
        config_snapshot = dispatch_claim.config_snapshot
        sdk_session_id = dispatch_claim.sdk_session_id
        permission_mode = dispatch_claim.permission_mode
        container_mode = dispatch_claim.container_mode
        container_id = dispatch_claim.container_id

        execution_context = self.execution_context_provider.get_context()
        ctx = {
            "run_id": run_id_str,
            "session_id": session_id,
            "user_id": user_id,
        }

        runtime_allocated = False

        try:
            resolved_config = await self.config_preparer.prepare_config(
                user_id=user_id,
                session_id=session_id,
                run_id=run_id_str,
                config_snapshot=config_snapshot,
            )

            step_started = time.perf_counter()
            browser_enabled = bool(resolved_config.get("browser_enabled"))
            (
                executor_url,
                container_id,
            ) = await self.runtime.allocate_runtime(
                session_id=session_id,
                user_id=user_id,
                browser_enabled=browser_enabled,
                container_mode=container_mode,
                container_id=container_id,
            )
            runtime_allocated = True
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_get_or_create_container",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "container_mode": container_mode,
                    "container_id": container_id,
                    "browser_enabled": browser_enabled,
                    **ctx,
                },
            )

            step_started = time.perf_counter()
            mcp_config = resolved_config.get("mcp_config")
            if isinstance(mcp_config, dict) and mcp_config:
                server_names = [str(name) for name in mcp_config]
                await self.state_gateway.record_mcp_staged_servers(
                    run_id=run_id_str,
                    session_id=session_id,
                    server_names=server_names,
                )

            step_started = time.perf_counter()
            running_lease_seconds = execution_context.running_lease_seconds
            await self.state_gateway.start_run(
                run_id=run_id, worker_id=worker_id, lease_seconds=running_lease_seconds
            )
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_backend_start_run",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "worker_id": worker_id,
                    "lease_seconds": running_lease_seconds,
                    **ctx,
                },
            )

            step_started = time.perf_counter()
            await self.executor_gateway.execute_run(
                executor_url=executor_url,
                session_id=session_id,
                run_id=run_id_str,
                prompt=prompt,
                execution_context=execution_context,
                config=resolved_config,
                sdk_session_id=sdk_session_id,
                permission_mode=permission_mode,
            )
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_executor_execute_task",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "container_id": container_id,
                    **ctx,
                },
            )

            logger.info(f"Dispatched run {run_id} (session={session_id})")
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_total",
                    "duration_ms": int((time.perf_counter() - dispatch_started) * 1000),
                    "container_mode": container_mode,
                    "container_id": container_id,
                    **ctx,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to dispatch run {run_id} (session={session_id}): "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            try:
                await self.state_gateway.fail_run(
                    run_id=run_id,
                    worker_id=worker_id,
                    error_message=str(e),
                )
            except Exception as fail_err:
                logger.error(f"Failed to mark run {run_id} as failed: {fail_err}")

            try:
                if runtime_allocated:
                    await self.runtime.cancel_runtime(session_id)
            except Exception as cancel_err:
                logger.error(
                    f"Failed to cancel task for session {session_id}: {cancel_err}"
                )
