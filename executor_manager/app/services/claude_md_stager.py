import logging
import time
from collections.abc import Callable

from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


def build_claude_md_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


class ClaudeMdStager:
    def __init__(
        self,
        workspace_manager: WorkspaceManager | None = None,
        *,
        workspace_manager_factory: Callable[[], WorkspaceManager] | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._workspace_manager_factory = (
            workspace_manager_factory or build_claude_md_workspace_manager
        )

    @property
    def workspace_manager(self) -> WorkspaceManager:
        if self._workspace_manager is None:
            self._workspace_manager = self._workspace_manager_factory()
        return self._workspace_manager

    @workspace_manager.setter
    def workspace_manager(self, value: WorkspaceManager) -> None:
        self._workspace_manager = value

    def stage(
        self,
        *,
        user_id: str,
        session_id: str,
        enabled: bool,
        content: str,
    ) -> dict[str, object]:
        """Stage user-level CLAUDE.md into workspace-level ~/.claude (symlinked by executor).

        The executor symlinks container `~/.claude` to `/workspace/.claude_data`, and
        the SDK loads it via `setting_sources=["user", "project"]`.
        """
        started_total = time.perf_counter()

        session_dir = self.workspace_manager.get_workspace_path(
            user_id=user_id, session_id=session_id, create=True
        )
        workspace_dir = session_dir / "workspace"
        claude_root = workspace_dir / ".claude_data"
        claude_root.mkdir(parents=True, exist_ok=True)

        target_file = (claude_root / "CLAUDE.md").resolve()
        claude_root_resolved = claude_root.resolve()
        if claude_root_resolved not in target_file.parents:
            raise ValueError("Invalid CLAUDE.md path")

        normalized = content if isinstance(content, str) else ""
        should_write = bool(enabled) and bool(normalized.strip())

        if should_write:
            # Keep file stable for the SDK and friendly in git-less workspaces.
            text = normalized
            if not text.endswith("\n"):
                text += "\n"
            target_file.write_text(text, encoding="utf-8")
            bytes_written = len(text.encode("utf-8"))
            logger.info(
                "timing",
                extra={
                    "step": "claude_md_stage_total",
                    "duration_ms": int((time.perf_counter() - started_total) * 1000),
                    "user_id": user_id,
                    "session_id": session_id,
                    "enabled": True,
                    "bytes": bytes_written,
                },
            )
            return {
                "enabled": True,
                "path": str(target_file),
                "bytes": bytes_written,
            }

        removed = False
        if target_file.exists():
            try:
                target_file.unlink()
                removed = True
            except Exception:
                removed = False

        logger.info(
            "timing",
            extra={
                "step": "claude_md_stage_total",
                "duration_ms": int((time.perf_counter() - started_total) * 1000),
                "user_id": user_id,
                "session_id": session_id,
                "enabled": False,
                "removed": removed,
            },
        )
        return {
            "enabled": False,
            "path": str(target_file),
            "removed": removed,
        }
