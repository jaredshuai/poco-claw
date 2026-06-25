"""Docker-backed ``ComputerProvider`` adapter.

Translates the provider-neutral ``ComputerProvider`` contract into the
existing ``ContainerPool`` surface.  This is the first concrete adapter
behind the new port; future Kubernetes / E2B / Cua providers will
implement the same protocol without touching this code.

The adapter intentionally stays thin — all Docker-specific orchestration
(image resolution, port mapping, health checks, label management) remains
inside ``ContainerPool``, which is the single Docker-aware leaf.
"""

from __future__ import annotations

from app.services.computer_provider import (
    ComputerCapability,
    ComputerInstance,
)
from app.services.run_dispatch_runtime import RunDispatchContainerPool


class DockerComputerProvider:
    """``ComputerProvider`` backed by a ``RunDispatchContainerPool``."""

    PROVIDER_NAME = "docker"

    def __init__(self, container_pool: RunDispatchContainerPool) -> None:
        self._pool = container_pool

    async def acquire(
        self,
        *,
        session_id: str,
        user_id: str,
        requires: set[ComputerCapability],
        reuse_id: str | None = None,
        mode: str = "ephemeral",
    ) -> ComputerInstance:
        browser_enabled = ComputerCapability.BROWSER in requires
        executor_url, container_id = await self._pool.get_or_create_container(
            session_id=session_id,
            user_id=user_id,
            browser_enabled=browser_enabled,
            container_mode=mode,
            container_id=reuse_id,
        )

        # Docker containers always provide shell + filesystem; add browser
        # only when it was requested (and therefore provisioned).
        capabilities = {ComputerCapability.SHELL, ComputerCapability.FILESYSTEM}
        if browser_enabled:
            capabilities.add(ComputerCapability.BROWSER)

        return ComputerInstance(
            instance_id=container_id or "",
            executor_endpoint=executor_url,
            provider=self.PROVIDER_NAME,
            capabilities=capabilities,
        )

    async def release(self, session_id: str) -> None:
        await self._pool.cancel_task(session_id)

    async def on_task_complete(self, session_id: str) -> None:
        await self._pool.on_task_complete(session_id)
