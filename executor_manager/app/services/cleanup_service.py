import logging
from collections.abc import Callable
from typing import Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class CleanupWorkspaceManager(Protocol):
    def cleanup_expired_workspaces(self) -> dict[str, int]: ...

    def get_disk_usage(self) -> dict[str, int | float | str]: ...


def build_cleanup_workspace_manager() -> CleanupWorkspaceManager:
    return WorkspaceManager()


class CleanupService:
    """Scheduled cleanup service."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        *,
        workspace_manager: CleanupWorkspaceManager | None = None,
        workspace_manager_factory: Callable[[], CleanupWorkspaceManager] | None = None,
    ):
        """Initialize cleanup service.

        Args:
            scheduler: APScheduler instance
        """
        self.scheduler = scheduler
        factory = workspace_manager_factory or build_cleanup_workspace_manager
        self.workspace_manager = (
            workspace_manager if workspace_manager is not None else factory()
        )

        self._schedule_cleanup_job()

    def _schedule_cleanup_job(self) -> None:
        """Schedule periodic cleanup job."""
        self.scheduler.add_job(
            self.cleanup_expired_workspaces,
            trigger="cron",
            hour=2,
            minute=0,
            id="cleanup-workspaces",
            replace_existing=True,
        )

        logger.info("Cleanup service initialized, scheduled daily at 02:00")

    async def cleanup_expired_workspaces(self) -> None:
        """Clean up expired workspaces."""
        logger.info("Starting workspace cleanup...")

        try:
            stats = self.workspace_manager.cleanup_expired_workspaces()

            logger.info(
                f"Workspace cleanup completed: "
                f"cleaned={stats['cleaned']}, "
                f"archived={stats['archived']}, "
                f"errors={stats['errors']}"
            )

            usage = self.workspace_manager.get_disk_usage()
            logger.info(
                f"Disk usage: {usage['usage_percent']}% "
                f"({usage['used_gb']}GB / {usage['total_gb']}GB)"
            )

        except Exception as e:
            logger.error(f"Workspace cleanup failed: {e}")
