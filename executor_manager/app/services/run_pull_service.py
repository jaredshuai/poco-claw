import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, cast

from app.core.settings import get_settings
from app.services.backend_client import BackendClient
from app.services.clock import Clock, SystemClock
from app.services.run_dispatch_claim import RunDispatchClaim
from app.services.run_dispatch_service import RunDispatchBackendClientPort
from app.services.run_dispatch_service import RunDispatchService
from app.services.run_dispatch_service import RunDispatchServiceSettings
from app.services.run_pull_queue_gateway import (
    BackendRunPullQueueGateway,
    RunPullQueueBackendClient,
    RunPullQueueGateway,
)
from app.services.worker_identity import get_worker_id

logger = logging.getLogger(__name__)

__all__ = ["RunPullService", "RunPullDispatchService", "RunPullBackendClientPort"]


class RunPullServiceSettings(RunDispatchServiceSettings, Protocol):
    """Settings port required by RunPullService.

    Combines dispatch service settings with pull-service-specific attributes.
    """

    max_concurrent_tasks: int
    task_claim_lease_seconds: int


class RunPullDispatchService(Protocol):
    """Minimal protocol for dispatch service dependency used by RunPullService."""

    async def dispatch_claim(
        self,
        claim: RunDispatchClaim | Mapping[str, Any],
        *,
        worker_id: str,
    ) -> None:
        """Dispatch a claimed run for execution."""
        ...


class RunPullBackendClientPort(
    RunPullQueueBackendClient,
    RunDispatchBackendClientPort,
    Protocol,
):
    """Combined backend client port for RunPullService dependencies."""

    pass


def build_run_pull_backend_client() -> RunPullBackendClientPort:
    return BackendClient()


def build_run_pull_dispatch_service(
    settings: RunPullServiceSettings, backend_client: RunPullBackendClientPort
) -> RunPullDispatchService:
    return RunDispatchService.create_default(
        settings=settings,
        backend_client=backend_client,
    )


def build_run_pull_queue_gateway(
    backend_client: RunPullBackendClientPort,
) -> RunPullQueueGateway:
    return BackendRunPullQueueGateway(backend_client)


class RunPullService:
    """Background service that pulls queued runs from Backend."""

    def __init__(
        self,
        *,
        settings: RunPullServiceSettings | None = None,
        backend_client: RunPullBackendClientPort | None = None,
        backend_client_factory: Callable[[], RunPullBackendClientPort] | None = None,
        queue_gateway: RunPullQueueGateway | None = None,
        queue_gateway_factory: Callable[[RunPullBackendClientPort], RunPullQueueGateway]
        | None = None,
        dispatch_service: RunPullDispatchService | None = None,
        dispatch_service_factory: Callable[
            [RunPullServiceSettings, RunPullBackendClientPort], RunPullDispatchService
        ]
        | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.settings = (
            settings
            if settings is not None
            else cast(RunPullServiceSettings, get_settings())
        )
        self._backend_client = backend_client
        self._backend_client_factory = (
            backend_client_factory or build_run_pull_backend_client
        )
        self._queue_gateway = queue_gateway
        self._queue_gateway_factory = (
            queue_gateway_factory or build_run_pull_queue_gateway
        )
        self._dispatch_service = dispatch_service
        self._dispatch_service_factory = (
            dispatch_service_factory or build_run_pull_dispatch_service
        )
        self.clock = clock or SystemClock()

        self.worker_id = get_worker_id()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_tasks)
        self._tasks: set[asyncio.Task[None]] = set()
        self._shutdown = False
        self._logged_started = False
        self._windows_until: dict[str, datetime] = {}
        self._window_locks: dict[str, asyncio.Lock] = {}
        self._inflight_run_ids: set[str] = set()
        self._inflight_lock = asyncio.Lock()

    def _get_backend_client(self) -> RunPullBackendClientPort:
        if self._backend_client is None:
            self._backend_client = self._backend_client_factory()
        return self._backend_client

    @property
    def queue_gateway(self) -> RunPullQueueGateway:
        if self._queue_gateway is None:
            self._queue_gateway = self._queue_gateway_factory(
                self._get_backend_client()
            )
        return self._queue_gateway

    @queue_gateway.setter
    def queue_gateway(self, value: RunPullQueueGateway) -> None:
        self._queue_gateway = value

    @property
    def dispatch_service(self) -> RunPullDispatchService:
        if self._dispatch_service is None:
            self._dispatch_service = self._dispatch_service_factory(
                self.settings,
                self._get_backend_client(),
            )
        return self._dispatch_service

    @dispatch_service.setter
    def dispatch_service(self, value: RunPullDispatchService) -> None:
        self._dispatch_service = value

    def _get_window_lock(self, window_id: str) -> asyncio.Lock:
        lock = self._window_locks.get(window_id)
        if lock is None:
            lock = asyncio.Lock()
            self._window_locks[window_id] = lock
        return lock

    async def _register_inflight_run(self, run_id: str) -> bool:
        async with self._inflight_lock:
            if run_id in self._inflight_run_ids:
                return False
            self._inflight_run_ids.add(run_id)
            return True

    async def _release_inflight_run(self, run_id: str) -> None:
        async with self._inflight_lock:
            self._inflight_run_ids.discard(run_id)

    def set_window_until(self, window_id: str, until_utc: datetime) -> None:
        if not window_id.strip():
            return
        if until_utc.tzinfo is None:
            until_utc = until_utc.replace(tzinfo=timezone.utc)
        self._windows_until[window_id] = until_utc.astimezone(timezone.utc)

    def _now_utc(self) -> datetime:
        now = self.clock.now_utc()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    async def open_window(
        self,
        window_id: str,
        schedule_modes: list[str] | None = None,
        window_minutes: int = 60,
    ) -> None:
        if self._shutdown:
            return
        window_id = window_id.strip()
        if not window_id:
            return

        if window_minutes <= 0:
            window_minutes = 60

        lock = self._get_window_lock(window_id)
        async with lock:
            now_utc = self._now_utc()
            until_utc = now_utc + timedelta(minutes=window_minutes)
            self._windows_until[window_id] = until_utc
            logger.info(
                f"Window opened (id={window_id}, until={until_utc.isoformat()}, schedule_modes={schedule_modes})"
            )

        await self.poll(schedule_modes=schedule_modes)

    async def poll_window(
        self,
        window_id: str,
        schedule_modes: list[str] | None = None,
    ) -> None:
        if self._shutdown:
            return
        window_id = window_id.strip()
        if not window_id:
            return

        until_utc = self._windows_until.get(window_id)
        if not until_utc:
            return

        now_utc = self._now_utc()
        if now_utc >= until_utc:
            self._windows_until.pop(window_id, None)
            return

        await self.poll(schedule_modes=schedule_modes)

    async def poll(self, schedule_modes: list[str] | None = None) -> None:
        """Poll backend run queue and dispatch as many as capacity allows."""
        if self._shutdown:
            return

        lease_seconds = max(5, int(self.settings.task_claim_lease_seconds))

        if not self._logged_started:
            logger.info(
                f"RunPullService started (worker_id={self.worker_id}, "
                f"lease={lease_seconds}s, max_concurrent={self.settings.max_concurrent_tasks})"
            )
            self._logged_started = True

        while not self._shutdown and not self._semaphore.locked():
            await self._semaphore.acquire()

            try:
                step_started = time.perf_counter()
                claim = await self.queue_gateway.claim_run(
                    worker_id=self.worker_id,
                    lease_seconds=lease_seconds,
                    schedule_modes=schedule_modes,
                )
                if claim:
                    logger.info(
                        "timing",
                        extra={
                            "step": "run_pull_claim_run",
                            "duration_ms": int(
                                (time.perf_counter() - step_started) * 1000
                            ),
                            "worker_id": self.worker_id,
                            "lease_seconds": lease_seconds,
                            "schedule_modes": schedule_modes,
                        },
                    )
            except asyncio.CancelledError:
                self._semaphore.release()
                return
            except Exception as e:
                logger.error(
                    "Failed to claim run from backend: %s: %r",
                    type(e).__name__,
                    e,
                )
                self._semaphore.release()
                return

            if not claim:
                self._semaphore.release()
                return

            task = asyncio.create_task(self._handle_claim(claim))
            self._tasks.add(task)
            task.add_done_callback(self._on_task_done)

    async def shutdown(self) -> None:
        """Request shutdown and cancel inflight dispatch tasks."""
        self._shutdown = True
        await self._drain_tasks()

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        self._semaphore.release()
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.error(f"Run dispatch task failed: {exc}")

    async def _drain_tasks(self) -> None:
        if not self._tasks:
            return
        tasks = list(self._tasks)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _handle_claim(self, claim: RunDispatchClaim) -> None:
        if not isinstance(claim, RunDispatchClaim):
            raise TypeError("RunPullService._handle_claim requires RunDispatchClaim")
        dispatch_claim = claim

        run_id_str = dispatch_claim.run_id_str
        if not await self._register_inflight_run(run_id_str):
            logger.warning(
                "Duplicate run claim detected while dispatch still in progress; skipping duplicate dispatch",
                extra={
                    "run_id": run_id_str,
                    "session_id": dispatch_claim.session_id,
                    "user_id": dispatch_claim.user_id,
                    "worker_id": self.worker_id,
                },
            )
            return

        try:
            await self.dispatch_service.dispatch_claim(
                dispatch_claim,
                worker_id=self.worker_id,
            )
        finally:
            await self._release_inflight_run(run_id_str)
