import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from app.core.settings import get_settings, resolve_executor_task_lease_secret
from app.scheduler.task_dispatcher import TaskDispatcher
from app.services.attachment_stager import AttachmentStager
from app.services.backend_client import BackendClient
from app.services.claude_md_stager import ClaudeMdStager
from app.services.config_resolver import ConfigResolver
from app.services.executor_client import ExecutorClient
from app.services.plugin_stager import PluginStager
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


class RunDispatchRuntime(Protocol):
    async def allocate_runtime(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> tuple[str, str | None]: ...

    async def cancel_runtime(self, session_id: str) -> None: ...


class RunDispatchConfigPreparer(Protocol):
    async def prepare_config(
        self,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        config_snapshot: dict[str, Any],
    ) -> dict[str, Any]: ...


class ContainerPoolRunDispatchRuntime:
    def __init__(self, container_pool: Any) -> None:
        self.container_pool = container_pool

    async def allocate_runtime(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> tuple[str, str | None]:
        return await self.container_pool.get_or_create_container(
            session_id=session_id,
            user_id=user_id,
            browser_enabled=browser_enabled,
            container_mode=container_mode,
            container_id=container_id,
        )

    async def cancel_runtime(self, session_id: str) -> None:
        await self.container_pool.cancel_task(session_id)


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


class StagingRunDispatchConfigPreparer:
    def __init__(
        self,
        *,
        backend_client: Any,
        config_resolver: Any,
        skill_stager: Any,
        plugin_stager: Any,
        attachment_stager: Any,
        claude_md_stager: Any,
        slash_command_stager: Any,
        subagent_stager: Any,
    ) -> None:
        self.backend_client = backend_client
        self.config_resolver = config_resolver
        self.skill_stager = skill_stager
        self.plugin_stager = plugin_stager
        self.attachment_stager = attachment_stager
        self.claude_md_stager = claude_md_stager
        self.slash_command_stager = slash_command_stager
        self.subagent_stager = subagent_stager

    async def prepare_config(
        self,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        config_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        ctx = {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
        }

        step_started = time.perf_counter()
        resolved_config = await self.config_resolver.resolve(
            user_id,
            config_snapshot,
            session_id=session_id,
            run_id=run_id,
        )
        logger.info(
            "timing",
            extra={
                "step": "run_dispatch_resolve_config",
                "duration_ms": int((time.perf_counter() - step_started) * 1000),
                **ctx,
            },
        )

        step_started = time.perf_counter()
        staged_skills = self.skill_stager.stage_skills(
            user_id=user_id,
            session_id=session_id,
            skills=resolved_config.get("skill_files") or {},
        )
        resolved_config["skill_files"] = staged_skills
        logger.info(
            "timing",
            extra={
                "step": "run_dispatch_stage_skills",
                "duration_ms": int((time.perf_counter() - step_started) * 1000),
                "skills_staged": len(staged_skills),
                **ctx,
            },
        )

        step_started = time.perf_counter()
        staged_plugins = self.plugin_stager.stage_plugins(
            user_id=user_id,
            session_id=session_id,
            plugins=resolved_config.get("plugin_files") or {},
        )
        resolved_config["plugin_files"] = staged_plugins
        logger.info(
            "timing",
            extra={
                "step": "run_dispatch_stage_plugins",
                "duration_ms": int((time.perf_counter() - step_started) * 1000),
                "plugins_staged": len(staged_plugins),
                **ctx,
            },
        )

        step_started = time.perf_counter()
        staged_inputs = self.attachment_stager.stage_inputs(
            user_id=user_id,
            session_id=session_id,
            inputs=resolved_config.get("input_files") or [],
        )
        resolved_config["input_files"] = staged_inputs
        logger.info(
            "timing",
            extra={
                "step": "run_dispatch_stage_inputs",
                "duration_ms": int((time.perf_counter() - step_started) * 1000),
                "inputs_staged": len(staged_inputs),
                **ctx,
            },
        )

        step_started = time.perf_counter()
        skill_names = _extract_enabled_skill_names(staged_skills)
        resolved_commands = await self.backend_client.resolve_slash_commands(
            user_id=user_id,
            skill_names=skill_names,
        )
        staged_commands = self.slash_command_stager.stage_commands(
            user_id=user_id,
            session_id=session_id,
            commands=resolved_commands,
        )
        logger.info(
            "timing",
            extra={
                "step": "run_dispatch_stage_slash_commands",
                "duration_ms": int((time.perf_counter() - step_started) * 1000),
                "commands_staged": len(staged_commands),
                **ctx,
            },
        )

        # Best-effort: don't block execution if CLAUDE.md staging fails.
        step_started = time.perf_counter()
        try:
            claude_md = await self.backend_client.get_claude_md(user_id=user_id)
            enabled = bool(claude_md.get("enabled"))
            content = (
                claude_md.get("content")
                if isinstance(claude_md.get("content"), str)
                else ""
            )
            staged_md = self.claude_md_stager.stage(
                user_id=user_id,
                session_id=session_id,
                enabled=enabled,
                content=content,
            )
            bytes_val = staged_md.get("bytes", 0)
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_stage_claude_md",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "enabled": bool(staged_md.get("enabled")),
                    "bytes": int(bytes_val) if isinstance(bytes_val, int) else 0,
                    **ctx,
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to stage CLAUDE.md for session {session_id}: {exc}")

        step_started = time.perf_counter()
        raw_agents_val = resolved_config.pop("subagent_raw_agents", None)
        raw_agents = raw_agents_val if isinstance(raw_agents_val, dict) else {}
        try:
            staged_agents = self.subagent_stager.stage_raw_agents(
                user_id=user_id,
                session_id=session_id,
                raw_agents=raw_agents,
            )
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_stage_subagents",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "subagents_requested": len(raw_agents),
                    "subagents_staged": len(staged_agents),
                    **ctx,
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to stage subagents for session {session_id}: {exc}")

        return resolved_config


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

    async def dispatch_claim(self, claim: dict[str, Any], *, worker_id: str) -> None:
        dispatch_started = time.perf_counter()
        run = claim.get("run") or {}
        run_id = run.get("run_id")
        session_id = run.get("session_id")
        scheduled_task_id = run.get("scheduled_task_id")
        user_id = claim.get("user_id") or ""
        prompt = claim.get("prompt") or ""
        config_snapshot = claim.get("config_snapshot") or {}
        sdk_session_id = None if scheduled_task_id else claim.get("sdk_session_id")
        permission_mode = str(run.get("permission_mode") or "default").strip()

        if not run_id or not session_id or not user_id or not prompt:
            logger.error(f"Invalid claim payload: {claim}")
            return

        run_id_str = str(run_id)
        container_mode = config_snapshot.get("container_mode", "ephemeral")
        container_id = config_snapshot.get("container_id")

        callback_base_url = (self.settings.callback_base_url or "").strip().rstrip("/")
        if not callback_base_url:
            raise ValueError("callback_base_url cannot be empty")
        callback_url = f"{callback_base_url}/api/v1/callback"
        ctx = {
            "run_id": run_id_str,
            "session_id": session_id,
            "user_id": user_id,
        }

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
                for server_name in mcp_config:
                    try:
                        await self.backend_client.record_mcp_transition(
                            run_id=str(run_id),
                            session_id=session_id,
                            server_name=server_name,
                            to_state="staged",
                            event_source="executor_manager",
                        )
                    except Exception:
                        pass

            step_started = time.perf_counter()
            await self.backend_client.start_run(run_id=run_id, worker_id=worker_id)
            logger.info(
                "timing",
                extra={
                    "step": "run_dispatch_backend_start_run",
                    "duration_ms": int((time.perf_counter() - step_started) * 1000),
                    "worker_id": worker_id,
                    **ctx,
                },
            )

            step_started = time.perf_counter()
            await self.executor_client.execute_task(
                executor_url=executor_url,
                session_id=session_id,
                run_id=str(run_id),
                prompt=prompt,
                callback_url=callback_url,
                callback_token=self.settings.callback_token,
                task_lease_secret=resolve_executor_task_lease_secret(self.settings),
                config=resolved_config,
                callback_base_url=callback_base_url,
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
                await self.backend_client.fail_run(
                    run_id=run_id,
                    worker_id=worker_id,
                    error_message=str(e),
                )
            except Exception as fail_err:
                logger.error(f"Failed to mark run {run_id} as failed: {fail_err}")

            try:
                if self._runtime is not None:
                    await self._runtime.cancel_runtime(session_id)
                elif self._container_pool is not None:
                    await ContainerPoolRunDispatchRuntime(
                        self._container_pool
                    ).cancel_runtime(session_id)
            except Exception as cancel_err:
                logger.error(
                    f"Failed to cancel task for session {session_id}: {cancel_err}"
                )
