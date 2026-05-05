import logging
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RunDispatchConfigPreparer(Protocol):
    async def prepare_config(
        self,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        config_snapshot: dict[str, Any],
    ) -> dict[str, Any]: ...


class BackendClientPort(Protocol):
    async def resolve_slash_commands(
        self,
        user_id: str,
        names: list[str] | None = None,
        skill_names: list[str] | None = None,
    ) -> dict[str, str]: ...

    async def get_claude_md(self, user_id: str) -> dict[str, Any]: ...


class ConfigResolverPort(Protocol):
    async def resolve(
        self,
        user_id: str,
        config_snapshot: dict[str, Any],
        *,
        session_id: str,
        run_id: str,
    ) -> dict[str, Any]: ...


class SkillStagerPort(Protocol):
    def stage_skills(
        self, *, user_id: str, session_id: str, skills: dict[str, Any]
    ) -> dict[str, Any]: ...


class PluginStagerPort(Protocol):
    def stage_plugins(
        self, *, user_id: str, session_id: str, plugins: dict[str, Any]
    ) -> dict[str, Any]: ...


class AttachmentStagerPort(Protocol):
    def stage_inputs(
        self, *, user_id: str, session_id: str, inputs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


class ClaudeMdStagerPort(Protocol):
    def stage(
        self, *, user_id: str, session_id: str, enabled: bool, content: str
    ) -> dict[str, Any]: ...


class SlashCommandStagerPort(Protocol):
    def stage_commands(
        self, *, user_id: str, session_id: str, commands: dict[str, str]
    ) -> dict[str, str]: ...


class SubagentStagerPort(Protocol):
    def stage_raw_agents(
        self, *, user_id: str, session_id: str, raw_agents: dict[str, str]
    ) -> dict[str, str]: ...


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
        backend_client: BackendClientPort,
        config_resolver: ConfigResolverPort,
        skill_stager: SkillStagerPort,
        plugin_stager: PluginStagerPort,
        attachment_stager: AttachmentStagerPort,
        claude_md_stager: ClaudeMdStagerPort,
        slash_command_stager: SlashCommandStagerPort,
        subagent_stager: SubagentStagerPort,
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
