import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from app.core.settings import get_settings
from app.services.backend_client import BackendClient

logger = logging.getLogger(__name__)


class ScheduledTaskBackendClient(Protocol):
    async def dispatch_due_scheduled_tasks(self, *, limit: int) -> dict[str, Any]: ...


class ScheduledTaskSettings(Protocol):
    scheduled_tasks_dispatch_batch_size: int


def build_scheduled_task_backend_client() -> ScheduledTaskBackendClient:
    return BackendClient()


class ScheduledTaskDispatchService:
    """Background service that asks Backend to enqueue due scheduled tasks."""

    def __init__(
        self,
        backend_client: ScheduledTaskBackendClient | None = None,
        *,
        backend_client_factory: Callable[[], ScheduledTaskBackendClient] | None = None,
        settings: ScheduledTaskSettings | None = None,
    ) -> None:
        self.settings = settings if settings is not None else get_settings()
        self._backend_client = backend_client
        self._backend_client_factory = (
            backend_client_factory or build_scheduled_task_backend_client
        )

    @property
    def backend_client(self) -> ScheduledTaskBackendClient:
        if self._backend_client is None:
            self._backend_client = self._backend_client_factory()
        return self._backend_client

    async def dispatch_due(self) -> None:
        started = time.perf_counter()
        batch_size = max(1, int(self.settings.scheduled_tasks_dispatch_batch_size))
        try:
            payload = await self.backend_client.dispatch_due_scheduled_tasks(
                limit=batch_size
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "scheduled_tasks_dispatch",
                extra={
                    "duration_ms": duration_ms,
                    "batch_size": batch_size,
                    "result": payload,
                },
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "scheduled_tasks_dispatch_failed",
                extra={
                    "duration_ms": duration_ms,
                    "batch_size": batch_size,
                    "error": str(e),
                },
            )
