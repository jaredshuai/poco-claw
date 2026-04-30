import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from app.core.settings import get_settings, resolve_executor_task_lease_secret
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
from app.services.container_pool import ContainerPool
from app.services.executor_client import ExecutorClient
from app.services.config_resolver import ConfigResolver
from app.services.skill_stager import SkillStager
from app.services.plugin_stager import PluginStager
from app.services.attachment_stager import AttachmentStager
from app.services.slash_command_stager import SlashCommandStager
from app.services.sub_agent_stager import SubAgentStager

logger = logging.getLogger(__name__)


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
        settings: Any | None = None,
        executor_client: Any | None = None,
        backend_client: Any | None = None,
        config_resolver: Any | None = None,
        skill_stager: Any | None = None,
        plugin_stager: Any | None = None,
        attachment_stager: Any | None = None,
        slash_command_stager: Any | None = None,
        subagent_stager: Any | None = None,
        runtime: TaskDispatchRuntime | None = None,
        executor_client_factory: Callable[[], Any] | None = None,
        backend_client_factory: Callable[[], Any] | None = None,
        config_resolver_factory: Callable[[Any, Any | None], Any] | None = None,
        skill_stager_factory: Callable[[], Any] | None = None,
        plugin_stager_factory: Callable[[], Any] | None = None,
        attachment_stager_factory: Callable[[], Any] | None = None,
        slash_command_stager_factory: Callable[[], Any] | None = None,
        subagent_stager_factory: Callable[[], Any] | None = None,
        runtime_factory: Callable[[], Any] | None = None,
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

    @property
    def executor_client(self) -> Any:
        if self._executor_client is None:
            self._executor_client = self._executor_client_factory()
        return self._executor_client

    @executor_client.setter
    def executor_client(self, value: Any) -> None:
        self._executor_client = value

    @property
    def backend_client(self) -> Any:
        if self._backend_client is None:
            self._backend_client = self._backend_client_factory()
        return self._backend_client

    @backend_client.setter
    def backend_client(self, value: Any) -> None:
        self._backend_client = value

    @property
    def config_resolver(self) -> Any:
        if self._config_resolver is None:
            self._config_resolver = self._config_resolver_factory(
                self.backend_client,
                self._settings,
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

    @property
    def runtime(self) -> TaskDispatchRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        return self._runtime

    @runtime.setter
    def runtime(self, value: TaskDispatchRuntime) -> None:
        self._runtime = value


def build_task_dispatch_backend_client() -> BackendClient:
    return BackendClient()


def build_task_dispatch_executor_client() -> ExecutorClient:
    return ExecutorClient()


def build_task_dispatch_config_resolver(
    backend_client: BackendClient,
    settings: Any | None = None,
) -> ConfigResolver:
    return ConfigResolver(backend_client, settings=settings)


def build_task_dispatch_skill_stager() -> SkillStager:
    return SkillStager()


def build_task_dispatch_plugin_stager() -> PluginStager:
    return PluginStager()


def build_task_dispatch_attachment_stager() -> AttachmentStager:
    return AttachmentStager()


def build_task_dispatch_slash_command_stager() -> SlashCommandStager:
    return SlashCommandStager()


def build_task_dispatch_subagent_stager() -> SubAgentStager:
    return SubAgentStager()


def build_task_dispatch_runtime() -> TaskDispatchRuntime:
    return TaskDispatcherRuntime()


def build_task_dispatch_container_pool() -> ContainerPool:
    return ContainerPool()


def build_task_dispatch_dependencies(
    *,
    settings: Any | None = None,
    executor_client_factory: Callable[[], Any] | None = None,
    backend_client_factory: Callable[[], Any] | None = None,
    config_resolver_factory: Callable[[Any, Any | None], Any] | None = None,
    skill_stager_factory: Callable[[], Any] | None = None,
    plugin_stager_factory: Callable[[], Any] | None = None,
    attachment_stager_factory: Callable[[], Any] | None = None,
    slash_command_stager_factory: Callable[[], Any] | None = None,
    subagent_stager_factory: Callable[[], Any] | None = None,
    runtime_factory: Callable[[], Any] | None = None,
) -> TaskDispatchDependencies:
    backend_factory = backend_client_factory or build_task_dispatch_backend_client
    executor_factory = executor_client_factory or build_task_dispatch_executor_client
    config_factory = config_resolver_factory or build_task_dispatch_config_resolver
    skill_factory = skill_stager_factory or build_task_dispatch_skill_stager
    plugin_factory = plugin_stager_factory or build_task_dispatch_plugin_stager
    attachment_factory = (
        attachment_stager_factory or build_task_dispatch_attachment_stager
    )
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
        slash_command_stager_factory=slash_command_factory,
        subagent_stager_factory=subagent_factory,
        runtime_factory=runtime_factory,
    )


def _extract_enabled_skill_names(skills: object) -> list[str]:
    if not isinstance(skills, dict):
        return []

    names: set[str] = set()
    for raw_name, spec in skills.items():
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if not name:
            continue
        if isinstance(spec, dict) and spec.get("enabled") is False:
            continue
        names.add(name)
    return sorted(names)


class TaskDispatcher:
    """Task dispatcher with container pool integration."""

    container_pool: ContainerPool | None = None
    container_pool_factory: Callable[[], ContainerPool] = (
        build_task_dispatch_container_pool
    )

    @classmethod
    def get_container_pool(cls) -> ContainerPool:
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
        settings: Any | None = None,
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
        settings = settings if settings is not None else get_settings()
        dispatch_dependencies = dependencies or build_task_dispatch_dependencies(
            settings=settings
        )
        executor_client = dispatch_dependencies.executor_client
        backend_client = dispatch_dependencies.backend_client
        config_resolver = dispatch_dependencies.config_resolver
        skill_stager = dispatch_dependencies.skill_stager
        plugin_stager = dispatch_dependencies.plugin_stager
        attachment_stager = dispatch_dependencies.attachment_stager
        slash_command_stager = dispatch_dependencies.slash_command_stager
        subagent_stager = dispatch_dependencies.subagent_stager
        runtime = dispatch_dependencies.runtime

        user_id = config.get("user_id", "")
        container_mode = config.get("container_mode", "ephemeral")
        container_id = config.get("container_id")

        callback_base_url = (settings.callback_base_url or "").strip().rstrip("/")
        if not callback_base_url:
            raise ValueError("callback_base_url cannot be empty")
        callback_url = f"{callback_base_url}/api/v1/callback"
        callback_token = settings.callback_token
        task_lease_secret = resolve_executor_task_lease_secret(settings)

        executor_url = None
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

            step_started = time.perf_counter()
            resolved_config = await config_resolver.resolve(
                user_id,
                config or {},
                session_id=session_id,
                task_id=task_id,
            )
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_resolve_config",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                },
            )

            step_started = time.perf_counter()
            staged_skills = skill_stager.stage_skills(
                user_id=user_id,
                session_id=session_id,
                skills=resolved_config.get("skill_files") or {},
            )
            resolved_config["skill_files"] = staged_skills
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_stage_skills",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "skills_staged": len(staged_skills),
                },
            )

            step_started = time.perf_counter()
            staged_plugins = plugin_stager.stage_plugins(
                user_id=user_id,
                session_id=session_id,
                plugins=resolved_config.get("plugin_files") or {},
            )
            resolved_config["plugin_files"] = staged_plugins
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_stage_plugins",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "plugins_staged": len(staged_plugins),
                },
            )

            step_started = time.perf_counter()
            staged_inputs = attachment_stager.stage_inputs(
                user_id=user_id,
                session_id=session_id,
                inputs=resolved_config.get("input_files") or [],
            )
            resolved_config["input_files"] = staged_inputs
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_stage_inputs",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "inputs_staged": len(staged_inputs),
                },
            )

            step_started = time.perf_counter()
            skill_names = _extract_enabled_skill_names(staged_skills)
            resolved_commands = await backend_client.resolve_slash_commands(
                user_id=user_id,
                skill_names=skill_names,
            )
            staged_commands = slash_command_stager.stage_commands(
                user_id=user_id,
                session_id=session_id,
                commands=resolved_commands,
            )
            logger.info(
                "timing",
                extra={
                    "step": "task_dispatch_stage_slash_commands",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "commands_staged": len(staged_commands),
                },
            )

            step_started = time.perf_counter()
            raw_agents_val = resolved_config.pop("subagent_raw_agents", None)
            raw_agents = raw_agents_val if isinstance(raw_agents_val, dict) else {}
            try:
                staged_agents = subagent_stager.stage_raw_agents(
                    user_id=user_id,
                    session_id=session_id,
                    raw_agents=raw_agents,
                )
                logger.info(
                    "timing",
                    extra={
                        "step": "task_dispatch_stage_subagents",
                        "duration_ms": int((time.perf_counter() - step_started) * 1000),
                        "task_id": task_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "subagents_requested": len(raw_agents),
                        "subagents_staged": len(staged_agents),
                    },
                )
            except Exception as exc:
                logger.warning(
                    f"Failed to stage subagents for session {session_id}: {exc}"
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
            await backend_client.update_session_status(session_id, "running")
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
            await executor_client.execute_task(
                executor_url=executor_url,
                session_id=session_id,
                run_id=None,
                prompt=prompt,
                callback_url=callback_url,
                callback_token=callback_token,
                task_lease_secret=task_lease_secret,
                config=resolved_config,
                callback_base_url=callback_base_url,
                sdk_session_id=sdk_session_id,
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
            await backend_client.update_session_status(session_id, "failed")
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
