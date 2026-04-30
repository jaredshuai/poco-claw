import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


def build_slash_command_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


class SlashCommandStager:
    def __init__(
        self,
        workspace_manager: WorkspaceManager | None = None,
        *,
        workspace_manager_factory: Callable[[], WorkspaceManager] | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._workspace_manager_factory = (
            workspace_manager_factory or build_slash_command_workspace_manager
        )

    @property
    def workspace_manager(self) -> WorkspaceManager:
        if self._workspace_manager is None:
            self._workspace_manager = self._workspace_manager_factory()
        return self._workspace_manager

    @workspace_manager.setter
    def workspace_manager(self, value: WorkspaceManager) -> None:
        self._workspace_manager = value

    @staticmethod
    def _validate_command_name(name: str) -> None:
        if name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Invalid slash command name: {name}",
            )

    @staticmethod
    def _clean_commands_dir(commands_root: Path) -> int:
        """Remove previously staged markdown files for this session."""
        removed = 0
        for entry in commands_root.iterdir():
            if entry.is_file() and entry.suffix == ".md":
                try:
                    entry.unlink()
                    removed += 1
                except Exception:
                    continue
        return removed

    def stage_commands(
        self,
        *,
        user_id: str,
        session_id: str,
        commands: dict[str, str],
    ) -> dict[str, str]:
        """Stage slash commands into workspace-level ~/.claude (symlinked by executor).

        Returns a map of command name -> local file path (string).
        """
        if not commands:
            return {}

        started_total = time.perf_counter()

        session_dir = self.workspace_manager.get_workspace_path(
            user_id=user_id, session_id=session_id, create=True
        )
        workspace_dir = session_dir / "workspace"
        commands_root = workspace_dir / ".claude_data" / "commands"
        commands_root.mkdir(parents=True, exist_ok=True)

        # Keep staging idempotent: commands that are disabled/deleted in backend should disappear.
        removed = self._clean_commands_dir(commands_root)

        staged: dict[str, str] = {}
        commands_root_resolved = commands_root.resolve()
        for name, markdown in commands.items():
            if not isinstance(markdown, str):
                continue
            self._validate_command_name(name)
            target_file = (commands_root / f"{name}.md").resolve()
            if commands_root_resolved not in target_file.parents:
                raise AppException(
                    error_code=ErrorCode.BAD_REQUEST,
                    message=f"Invalid slash command path: {name}",
                )
            try:
                target_file.write_text(markdown, encoding="utf-8")
                staged[name] = str(target_file)
            except Exception as exc:
                raise AppException(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=f"Failed to stage slash command {name}: {exc}",
                ) from exc

        logger.info(
            "timing",
            extra={
                "step": "slash_command_stage_total",
                "duration_ms": int((time.perf_counter() - started_total) * 1000),
                "user_id": user_id,
                "session_id": session_id,
                "commands_requested": len(commands),
                "commands_staged": len(staged),
                "commands_removed": removed,
            },
        )
        return staged
