import logging
import time
from collections.abc import Callable
from typing import Any, Protocol, cast

from app.core.settings import get_settings
from app.core.observability.request_context import (
    generate_request_id,
    generate_trace_id,
    get_request_id,
    get_trace_id,
    reset_request_id,
    reset_trace_id,
    set_request_id,
    set_trace_id,
)
from app.services.backend_client import BackendClient
from app.services.claude_md_stager import ClaudeMdStager
from app.services.container_pool import ContainerPool
from app.services.executor_client import ExecutorClient
from app.services.config_resolver import ConfigBackendClient
from app.services.config_resolver import ConfigResolver
from app.services.config_resolver import ConfigResolverSettings
from app.services.skill_stager import SkillStager
from app.services.plugin_stager import PluginStager
from app.services.attachment_stager import AttachmentStager
from app.services.run_dispatch_executor_gateway import (
    RunDispatchExecutorClientPort,
)
from app.services.run_dispatch_config_preparer import (
    AttachmentStagerPort,
    BackendClientPort as ConfigBackendClientPort,
    ClaudeMdStagerPort,
    ConfigResolverPort,
    PluginStagerPort,
    RunDispatchConfigPreparer,
    SkillStagerPort,
    SlashCommandStagerPort,
    StagingRunDispatchConfigPreparer,
    SubagentStagerPort,
)
from app.services.run_dispatch_execution_context import (
    RunDispatchExecutionContext,
    RunDispatchExecutionContextProvider,
    RunDispatchExecutionContextSettings,
    SettingsRunDispatchExecutionContextProvider,
)
from app.services.slash_command_stager import SlashCommandStager
from app.services.sub_agent_stager import SubAgentStager
from app.services.task_dispatch_state_gateway import (
    BackendClientPort as StateBackendClientPort,
    BackendTaskDispatchStateGateway,
    TaskDispatchStateGateway,
)


class TaskDispatchSettings(
    ConfigResolverSettings,
    RunDispatchExecutionContextSettings,
    Protocol,
):
    """Settings required by the scheduler dispatch path."""

    task_timeout_seconds: int | None


class TaskDispatchBackendClientPort(
    ConfigBackendClient,
    ConfigBackendClientPort,
    StateBackendClientPort,
    Protocol,
):
    pass


class LegacyTaskDispatchExecutorGateway(Protocol):
    """Legacy executor gateway port for TaskDispatcher that accepts optional run_id."""

    async def execute_run(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str | None,
        prompt: str,
        execution_context: RunDispatchExecutionContext,
        config: dict[str, Any],
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str: ...


class ExecutorClientLegacyTaskDispatchGateway:
    """Adapter that adapts RunDispatchExecutorClientPort to LegacyTaskDispatchExecutorGateway."""

    def __init__(self, executor_client: RunDispatchExecutorClientPort) -> None:
        self.executor_client = executor_client

    async def execute_run(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str | None,
        prompt: str,
        execution_context: RunDispatchExecutionContext,
        config: dict[str, Any],
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str:
        return await self.executor_client.execute_task(
            executor_url=executor_url,
            session_id=session_id,
            run_id=run_id,
            prompt=prompt,
            callback_url=execution_context.callback_url,
            callback_token=execution_context.callback_token,
            task_lease_secret=execution_context.task_lease_secret,
            config=config,
            callback_base_url=execution_context.callback_base_url,
            sdk_session_id=sdk_session_id,
            permission_mode=permission_mode,
        )


logger = logging.getLogger(__name__)


class ContainerPoolCapability(Protocol):
    """Minimal protocol for container-pool capability used by TaskDispatcher."""

    async def get_or_create_container(
        self,
        session_id: str,
        user_id: str,
        *,
        browser_enabled: bool = False,
        container_mode: str = "ephemeral",
        container_id: str | None = None,
    ) -> tuple[str, str]: ...

    async def cancel_task(self, session_id: str) -> None: ...

    async def delete_container(self, container_id: str) -> None: ...

    def get_container_stats(self) -> Any: ...

    async def on_task_complete(self, session_id: str) -> None: ...


class TaskDispatchRuntime(Protocol):
    async def resolve_executor_target(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> tuple[str, str | None]: ...

    async def cancel_task(self, session_id: str) -> None: ...


class TaskDispatcherRuntime:
    async def resolve_executor_target(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> tuple[str, str | None]:
        return await TaskDispatcher.resolve_executor_target(
            session_id=session_id,
            user_id=user_id,
            browser_enabled=browser_enabled,
            container_mode=container_mode,
            container_id=container_id,
        )

    async def cancel_task(self, session_id: str) -> None:
        await TaskDispatcher.get_container_pool().cancel_task(session_id)


class TaskDispatchDependencies:
    def __init__(
        self,
        *,
        settings: TaskDispatchSettings | None = None,
        executor_client: RunDispatchExecutorClientPort | None = None,
        backend_client: TaskDispatchBackendClientPort | None = None,
        config_resolver: ConfigResolverPort | None = None,
        skill_stager: SkillStagerPort | None = None,
        plugin_stager: PluginStagerPort | None = None,
        attachment_stager: AttachmentStagerPort | None = None,
        claude_md_stager: ClaudeMdStagerPort | None = None,
        slash_command_stager: SlashCommandStagerPort | None = None,
        subagent_stager: SubagentStagerPort | None = None,
        runtime: TaskDispatchRuntime | None = None,
        config_preparer: RunDispatchConfigPreparer | None = None,
        executor_gateway: LegacyTaskDispatchExecutorGateway | None = None,
        state_gateway: TaskDispatchStateGateway | None = None,
        execution_context_provider: RunDispatchExecutionContextProvider | None = None,
        executor_client_factory: Callable[[], RunDispatchExecutorClientPort]
        | None = None,
        backend_client_factory: Callable[[], TaskDispatchBackendClientPort]
        | None = None,
        config_resolver_factory: Callable[
            [TaskDispatchBackendClientPort, TaskDispatchSettings | None],
            ConfigResolverPort,
        ]
        | None = None,
        skill_stager_factory: Callable[[], SkillStagerPort] | None = None,
        plugin_stager_factory: Callable[[], PluginStagerPort] | None = None,
        attachment_stager_factory: Callable[[], AttachmentStagerPort] | None = None,
        claude_md_stager_factory: Callable[[], ClaudeMdStagerPort] | None = None,
        slash_command_stager_factory: Callable[[], SlashCommandStagerPort]
        | None = None,
        subagent_stager_factory: Callable[[], SubagentStagerPort] | None = None,
        runtime_factory: Callable[[], TaskDispatchRuntime] | None = None,
        config_preparer_factory: Callable[[], RunDispatchConfigPreparer] | None = None,
        executor_gateway_factory: Callable[[], LegacyTaskDispatchExecutorGateway]
        | None = None,
        state_gateway_factory: Callable[[], TaskDispatchStateGateway] | None = None,
        execution_context_provider_factory: Callable[
            [], RunDispatchExecutionContextProvider
        ]
        | None = None,
    ) -> None:
        self._settings = settings
        self._executor_client = executor_client
        self._executor_client_factory = (
            executor_client_factory or build_task_dispatch_executor_client
        )
        self._backend_client = backend_client
        self._backend_client_factory = (
            backend_client_factory or build_task_dispatch_backend_client
        )
        self._config_resolver = config_resolver
        self._config_resolver_factory = (
            config_resolver_factory or build_task_dispatch_config_resolver
        )
        self._skill_stager = skill_stager
        self._skill_stager_factory = (
            skill_stager_factory or build_task_dispatch_skill_stager
        )
        self._plugin_stager = plugin_stager
        self._plugin_stager_factory = (
            plugin_stager_factory or build_task_dispatch_plugin_stager
        )
        self._attachment_stager = attachment_stager
        self._attachment_stager_factory = (
            attachment_stager_factory or build_task_dispatch_attachment_stager
        )
        self._claude_md_stager = claude_md_stager
        self._claude_md_stager_factory = (
            claude_md_stager_factory or build_task_dispatch_claude_md_stager
        )
        self._slash_command_stager = slash_command_stager
        self._slash_command_stager_factory = (
            slash_command_stager_factory or build_task_dispatch_slash_command_stager
        )
        self._subagent_stager = subagent_stager
        self._subagent_stager_factory = (
            subagent_stager_factory or build_task_dispatch_subagent_stager
        )
        self._runtime = runtime
        self._runtime_factory = runtime_factory or build_task_dispatch_runtime
        self._config_preparer = config_preparer
        self._config_preparer_factory = config_preparer_factory
        self._executor_gateway = executor_gateway
        self._executor_gateway_factory = executor_gateway_factory
        self._state_gateway = state_gateway
        self._state_gateway_factory = state_gateway_factory
        self._execution_context_provider = execution_context_provider
        self._execution_context_provider_factory = execution_context_provider_factory

    @property
    def executor_client(self) -> RunDispatchExecutorClientPort:
        if self._executor_client is None:
            self._executor_client = self._executor_client_factory()
        return self._executor_client

    @executor_client.setter
    def executor_client(self, value: RunDispatchExecutorClientPort) -> None:
        self._executor_client = value

    @property
    def backend_client(self) -> TaskDispatchBackendClientPort:
        if self._backend_client is None:
            self._backend_client = self._backend_client_factory()
        return self._backend_client

    @backend_client.setter
    def backend_client(self, value: TaskDispatchBackendClientPort) -> None:
        self._backend_client = value

    @property
    def config_resolver(self) -> ConfigResolverPort:
        if self._config_resolver is None:
            self._config_resolver = self._config_resolver_factory(
                self.backend_client,
                self._settings,
            )
        return self._config_resolver

    @config_resolver.setter
    def config_resolver(self, value: ConfigResolverPort) -> None:
        self._config_resolver = value

    @property
    def skill_stager(self) -> SkillStagerPort:
        if self._skill_stager is None:
            self._skill_stager = self._skill_stager_factory()
        return self._skill_stager

    @skill_stager.setter
    def skill_stager(self, value: SkillStagerPort) -> None:
        self._skill_stager = value

    @property
    def plugin_stager(self) -> PluginStagerPort:
        if self._plugin_stager is None:
            self._plugin_stager = self._plugin_stager_factory()
        return self._plugin_stager

    @plugin_stager.setter
    def plugin_stager(self, value: PluginStagerPort) -> None:
        self._plugin_stager = value

    @property
    def attachment_stager(self) -> AttachmentStagerPort:
        if self._attachment_stager is None:
            self._attachment_stager = self._attachment_stager_factory()
        return self._attachment_stager

    @attachment_stager.setter
    def attachment_stager(self, value: AttachmentStagerPort) -> None:
        self._attachment_stager = value

    @property
    def claude_md_stager(self) -> ClaudeMdStagerPort:
        if self._claude_md_stager is None:
            self._claude_md_stager = self._claude_md_stager_factory()
        return self._claude_md_stager

    @claude_md_stager.setter
    def claude_md_stager(self, value: ClaudeMdStagerPort) -> None:
        self._claude_md_stager = value

    @property
    def slash_command_stager(self) -> SlashCommandStagerPort:
        if self._slash_command_stager is None:
            self._slash_command_stager = self._slash_command_stager_factory()
        return self._slash_command_stager

    @slash_command_stager.setter
    def slash_command_stager(self, value: SlashCommandStagerPort) -> None:
        self._slash_command_stager = value

    @property
    def subagent_stager(self) -> SubagentStagerPort:
        if self._subagent_stager is None:
            self._subagent_stager = self._subagent_stager_factory()
        return self._subagent_stager

    @subagent_stager.setter
    def subagent_stager(self, value: SubagentStagerPort) -> None:
        self._subagent_stager = value

    @property
    def runtime(self) -> TaskDispatchRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        return self._runtime

    @runtime.setter
    def runtime(self, value: TaskDispatchRuntime) -> None:
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
    def config_preparer(self, value: RunDispatchConfigPreparer | None) -> None:
        self._config_preparer = value

    @property
    def executor_gateway(self) -> LegacyTaskDispatchExecutorGateway:
        if (
            self._executor_gateway is None
            and self._executor_gateway_factory is not None
        ):
            self._executor_gateway = self._executor_gateway_factory()
        if self._executor_gateway is None:
            self._executor_gateway = ExecutorClientLegacyTaskDispatchGateway(
                self.executor_client
            )
        return self._executor_gateway

    @executor_gateway.setter
    def executor_gateway(self, value: LegacyTaskDispatchExecutorGateway) -> None:
        self._executor_gateway = value

    @property
    def state_gateway(self) -> TaskDispatchStateGateway:
        if self._state_gateway is None and self._state_gateway_factory is not None:
            self._state_gateway = self._state_gateway_factory()
        if self._state_gateway is None:
            self._state_gateway = BackendTaskDispatchStateGateway(self.backend_client)
        return self._state_gateway

    @state_gateway.setter
    def state_gateway(self, value: TaskDispatchStateGateway) -> None:
        self._state_gateway = value

    def bind_settings_if_unset(self, settings: TaskDispatchSettings) -> None:
        if self._settings is None:
            self._settings = settings

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
                SettingsRunDispatchExecutionContextProvider(
                    cast(TaskDispatchSettings, self._settings)
                )
            )
        return self._execution_context_provider

    @execution_context_provider.setter
    def execution_context_provider(
        self,
        value: RunDispatchExecutionContextProvider,
    ) -> None:
        self._execution_context_provider = value


def build_task_dispatch_backend_client() -> TaskDispatchBackendClientPort:
    return BackendClient()


def build_task_dispatch_executor_client() -> RunDispatchExecutorClientPort:
    return ExecutorClient()


def build_task_dispatch_config_resolver(
    backend_client: TaskDispatchBackendClientPort,
    settings: TaskDispatchSettings | None = None,
) -> ConfigResolverPort:
    return ConfigResolver(backend_client, settings=settings)


def build_task_dispatch_skill_stager() -> SkillStagerPort:
    return SkillStager()


def build_task_dispatch_plugin_stager() -> PluginStagerPort:
    return PluginStager()


def build_task_dispatch_attachment_stager() -> AttachmentStagerPort:
    return AttachmentStager()


def build_task_dispatch_claude_md_stager() -> ClaudeMdStagerPort:
    return ClaudeMdStager()


def build_task_dispatch_slash_command_stager() -> SlashCommandStagerPort:
    return SlashCommandStager()


def build_task_dispatch_subagent_stager() -> SubagentStagerPort:
    return SubAgentStager()


def build_task_dispatch_runtime() -> TaskDispatchRuntime:
    return TaskDispatcherRuntime()


def build_task_dispatch_container_pool() -> ContainerPoolCapability:
    return ContainerPool()


def build_task_dispatch_dependencies(
    *,
    settings: TaskDispatchSettings | None = None,
    executor_client_factory: Callable[[], RunDispatchExecutorClientPort] | None = None,
    backend_client_factory: Callable[[], TaskDispatchBackendClientPort] | None = None,
    config_resolver_factory: Callable[
        [TaskDispatchBackendClientPort, TaskDispatchSettings | None], ConfigResolverPort
    ]
    | None = None,
    skill_stager_factory: Callable[[], SkillStagerPort] | None = None,
    plugin_stager_factory: Callable[[], PluginStagerPort] | None = None,
    attachment_stager_factory: Callable[[], AttachmentStagerPort] | None = None,
    claude_md_stager_factory: Callable[[], ClaudeMdStagerPort] | None = None,
    slash_command_stager_factory: Callable[[], SlashCommandStagerPort] | None = None,
    subagent_stager_factory: Callable[[], SubagentStagerPort] | None = None,
    runtime_factory: Callable[[], TaskDispatchRuntime] | None = None,
    config_preparer_factory: Callable[[], RunDispatchConfigPreparer] | None = None,
    executor_gateway_factory: Callable[[], LegacyTaskDispatchExecutorGateway]
    | None = None,
    state_gateway_factory: Callable[[], TaskDispatchStateGateway] | None = None,
    execution_context_provider_factory: Callable[
        [], RunDispatchExecutionContextProvider
    ]
    | None = None,
) -> TaskDispatchDependencies:
    backend_factory = backend_client_factory or build_task_dispatch_backend_client
    executor_factory = executor_client_factory or build_task_dispatch_executor_client
    config_factory = config_resolver_factory or build_task_dispatch_config_resolver
    skill_factory = skill_stager_factory or build_task_dispatch_skill_stager
    plugin_factory = plugin_stager_factory or build_task_dispatch_plugin_stager
    attachment_factory = (
        attachment_stager_factory or build_task_dispatch_attachment_stager
    )
    claude_md_factory = claude_md_stager_factory or build_task_dispatch_claude_md_stager
    slash_command_factory = (
        slash_command_stager_factory or build_task_dispatch_slash_command_stager
    )
    subagent_factory = subagent_stager_factory or build_task_dispatch_subagent_stager
    runtime_factory = runtime_factory or build_task_dispatch_runtime
    return TaskDispatchDependencies(
        settings=settings,
        executor_client_factory=executor_factory,
        backend_client_factory=backend_factory,
        config_resolver_factory=config_factory,
        skill_stager_factory=skill_factory,
        plugin_stager_factory=plugin_factory,
        attachment_stager_factory=attachment_factory,
        claude_md_stager_factory=claude_md_factory,
        slash_command_stager_factory=slash_command_factory,
        subagent_stager_factory=subagent_factory,
        runtime_factory=runtime_factory,
        config_preparer_factory=config_preparer_factory,
        executor_gateway_factory=executor_gateway_factory,
        state_gateway_factory=state_gateway_factory,
        execution_context_provider_factory=execution_context_provider_factory,
    )


class TaskDispatcher:
    """Task dispatcher with container pool integration."""

    container_pool: ContainerPoolCapability | None = None
    container_pool_factory: Callable[[], ContainerPoolCapability] = (
        build_task_dispatch_container_pool
    )

    @classmethod
    def get_container_pool(cls) -> ContainerPoolCapability:
        """Get container pool instance (lazy load)."""
        if cls.container_pool is None:
            cls.container_pool = cls.container_pool_factory()
        return cls.container_pool

    @classmethod
    async def resolve_executor_target(
        cls,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> tuple[str, str | None]:
        container_pool = cls.get_container_pool()
        return await container_pool.get_or_create_container(
            session_id=session_id,
            user_id=user_id,
            browser_enabled=browser_enabled,
            container_mode=container_mode,
            container_id=container_id,
        )

    @staticmethod
    async def dispatch(
        task_id: str,
        session_id: str,
        prompt: str,
        config: dict,
        sdk_session_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        enqueued_at: float | None = None,
        dependencies: TaskDispatchDependencies | None = None,
        settings: TaskDispatchSettings | None = None,
    ) -> None:
        """Dispatch task to executor.

        Args:
            task_id: Task ID
            session_id: Session ID
            prompt: Task prompt
            config: Task configuration
            sdk_session_id: Claude SDK session ID for resuming conversations
            request_id: Request ID for correlating logs across async boundaries
            trace_id: Trace ID for correlating logs across async boundaries
            enqueued_at: perf_counter timestamp when the task was enqueued (for queue delay)
        """
        settings = (
            settings
            if settings is not None
            else cast(TaskDispatchSettings, get_settings())
        )
        dispatch_dependencies = dependencies or build_task_dispatch_dependencies(
            settings=settings
        )
        dispatch_dependencies.bind_settings_if_unset(settings)
        executor_gateway = dispatch_dependencies.executor_gateway
        state_gateway = dispatch_dependencies.state_gateway
        config_preparer = dispatch_dependencies.config_preparer
        runtime = dispatch_dependencies.runtime
        execution_context = (
            dispatch_dependencies.execution_context_provider.get_context()
        )

        user_id = config.get("user_id", "")
        container_mode = config.get("container_mode", "ephemeral")
        container_id = config.get("container_id")

        executor_url = None
        runtime_resolved = False
        request_id_token = set_request_id(
            request_id or get_request_id() or generate_request_id()
        )
        trace_id_token = set_trace_id(trace_id or get_trace_id() or generate_trace_id())
        try:
            dispatch_started = time.perf_counter()
            if enqueued_at is not None:
                logger.info(
                    "timing",
                    extra={
                        "step": "task_dispatch_queue_delay",
                        "duration_ms": int((time.perf_counter() - enqueued_at) * 1000),
                        "task_id": task_id,
                        "session_id": session_id,
                        "user_id": user_id,
                    },
                )

            logger.info(
                f"Dispatching task {task_id} (session: {session_id}, mode: {container_mode})"
            )

            resolved_config = await config_preparer.prepare_config(
                user_id=user_id,
                session_id=session_id,
                run_id=task_id,
                config_snapshot=config,
            )

            step_started = time.perf_counter()
            browser_enabled = bool(resolved_config.get("browser_enabled"))
            executor_url, container_id = await runtime.resolve_executor_target(
                session_id=session_id,
                user_id=user_id,
                browser_enabled=browser_enabled,
                container_mode=container_mode,
                container_id=container_id,
            )
            runtime_resolved = True
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_get_or_create_container",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "container_id": container_id,
                    "container_mode": container_mode,
                    "browser_enabled": browser_enabled,
                },
            )

            step_started = time.perf_counter()
            await state_gateway.mark_running(session_id=session_id)
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_backend_update_status_running",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                },
            )

            step_started = time.perf_counter()
            await executor_gateway.execute_run(
                executor_url=executor_url,
                session_id=session_id,
                run_id=None,
                prompt=prompt,
                execution_context=execution_context,
                config=resolved_config,
                sdk_session_id=sdk_session_id,
                permission_mode="default",
            )
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_executor_execute_task",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "container_id": container_id,
                },
            )

            logger.info(f"Task {task_id} dispatched successfully to executor")
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_total",
                    "duration_ms": int((time.perf_counter() - dispatch_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "container_id": container_id,
                    "container_mode": container_mode,
                },
            )

        except Exception as e:
            logger.error(f"Failed to dispatch task {task_id}: {e}")
            await state_gateway.mark_failed(session_id=session_id)
            if runtime_resolved:
                await runtime.cancel_task(session_id)
            raise
        finally:
            reset_request_id(request_id_token)
            reset_trace_id(trace_id_token)

    @staticmethod
    async def on_task_complete(session_id: str) -> None:
        """Handle task completion.

        Args:
            session_id: Session ID
        """
        container_pool = TaskDispatcher.get_container_pool()
        await container_pool.on_task_complete(session_id)
