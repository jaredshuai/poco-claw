import asyncio
import logging
import os
import socket
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.settings import get_settings
from app.services.backend_client import BackendClient
from app.services.clock import Clock, SystemClock
from app.services.run_dispatch_service import RunDispatchService

logger = logging.getLogger(__name__)

__all__ = ["RunPullService"]


def build_run_pull_backend_client() -> Any:
    return BackendClient()


class RunPullService:
    """Background service that pulls queued runs from Backend."""

    def __init__(
        self,
        *,
        settings: Any | None = None,
        backend_client: Any | None = None,
        backend_client_factory: Callable[[], Any] | None = None,
        dispatch_service: Any | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings if settings is not None else get_settings()
        self._backend_client = backend_client
        self._backend_client_factory = (
            backend_client_factory or build_run_pull_backend_client
        )
        self._dispatch_service = dispatch_service
        self.clock = clock or SystemClock()

        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_tasks)
        self._tasks: set[asyncio.Task[None]] = set()
        self._shutdown = False
        self._logged_started = False
        self._windows_until: dict[str, datetime] = {}
        self._window_locks: dict[str, asyncio.Lock] = {}
        self._inflight_run_ids: set[str] = set()
        self._inflight_lock = asyncio.Lock()

    @property
    def backend_client(self) -> Any:
        if self._backend_client is None:
            self._backend_client = self._backend_client_factory()
        return self._backend_client

    @backend_client.setter
    def backend_client(self, value: Any) -> None:
        self._backend_client = value

    @property
    def dispatch_service(self) -> Any:
        if self._dispatch_service is None:
            self._dispatch_service = RunDispatchService.create_default(
                settings=self.settings,
                backend_client=self.backend_client,
            )
        return self._dispatch_service

    @dispatch_service.setter
    def dispatch_service(self, value: Any) -> None:
        self._dispatch_service = value

    @property
    def executor_client(self) -> Any:
        return getattr(self.dispatch_service, "executor_client", None)

    @executor_client.setter
    def executor_client(self, value: Any) -> None:
        setattr(self.dispatch_service, "executor_client", value)

    @property
    def container_pool(self) -> Any:
        return getattr(self.dispatch_service, "container_pool", None)

    @container_pool.setter
    def container_pool(self, value: Any) -> None:
        setattr(self.dispatch_service, "container_pool", value)

    @property
    def config_resolver(self) -> Any:
        return getattr(self.dispatch_service, "config_resolver", None)

    @config_resolver.setter
    def config_resolver(self, value: Any) -> None:
        setattr(self.dispatch_service, "config_resolver", value)

    @property
    def skill_stager(self) -> Any:
        return getattr(self.dispatch_service, "skill_stager", None)

    @skill_stager.setter
    def skill_stager(self, value: Any) -> None:
        setattr(self.dispatch_service, "skill_stager", value)

    @property
    def plugin_stager(self) -> Any:
        return getattr(self.dispatch_service, "plugin_stager", None)

    @plugin_stager.setter
    def plugin_stager(self, value: Any) -> None:
        setattr(self.dispatch_service, "plugin_stager", value)

    @property
    def attachment_stager(self) -> Any:
        return getattr(self.dispatch_service, "attachment_stager", None)

    @attachment_stager.setter
    def attachment_stager(self, value: Any) -> None:
        setattr(self.dispatch_service, "attachment_stager", value)

    @property
    def claude_md_stager(self) -> Any:
        return getattr(self.dispatch_service, "claude_md_stager", None)

    @claude_md_stager.setter
    def claude_md_stager(self, value: Any) -> None:
        setattr(self.dispatch_service, "claude_md_stager", value)

    @property
    def slash_command_stager(self) -> Any:
        return getattr(self.dispatch_service, "slash_command_stager", None)

    @slash_command_stager.setter
    def slash_command_stager(self, value: Any) -> None:
        setattr(self.dispatch_service, "slash_command_stager", value)

    @property
    def subagent_stager(self) -> Any:
        return getattr(self.dispatch_service, "subagent_stager", None)

    @subagent_stager.setter
    def subagent_stager(self, value: Any) -> None:
        setattr(self.dispatch_service, "subagent_stager", value)

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
                claim = await self.backend_client.claim_run(
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

    async def _handle_claim(self, claim: dict[str, Any]) -> None:
        run = claim.get("run") or {}
        run_id = run.get("run_id")
        session_id = run.get("session_id")
        user_id = claim.get("user_id") or ""
        prompt = claim.get("prompt") or ""

        if not run_id or not session_id or not user_id or not prompt:
            logger.error(f"Invalid claim payload: {claim}")
            return

        run_id_str = str(run_id)
        if not await self._register_inflight_run(run_id_str):
            logger.warning(
                "Duplicate run claim detected while dispatch still in progress; skipping duplicate dispatch",
                extra={
                    "run_id": run_id_str,
                    "session_id": session_id,
                    "user_id": user_id,
                    "worker_id": self.worker_id,
                },
            )
            return

        try:
            await self.dispatch_service.dispatch_claim(
                claim,
                worker_id=self.worker_id,
            )
        finally:
            await self._release_inflight_run(run_id_str)
