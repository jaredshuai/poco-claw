from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RunDispatchRuntimeAllocation:
    executor_url: str
    container_id: str | None


class RunDispatchContainerPool(Protocol):
    async def get_or_create_container(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> tuple[str, str | None]: ...

    async def cancel_task(self, session_id: str) -> None: ...

    async def on_task_complete(self, session_id: str) -> None: ...


class RunDispatchRuntime(Protocol):
    async def allocate_runtime(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> RunDispatchRuntimeAllocation: ...

    async def cancel_runtime(self, session_id: str) -> None: ...


class ContainerPoolRunDispatchRuntime:
    def __init__(self, container_pool: RunDispatchContainerPool) -> None:
        self.container_pool = container_pool

    async def allocate_runtime(
        self,
        *,
        session_id: str,
        user_id: str,
        browser_enabled: bool,
        container_mode: str,
        container_id: str | None,
    ) -> RunDispatchRuntimeAllocation:
        (
            executor_url,
            allocated_container_id,
        ) = await self.container_pool.get_or_create_container(
            session_id=session_id,
            user_id=user_id,
            browser_enabled=browser_enabled,
            container_mode=container_mode,
            container_id=container_id,
        )
        return RunDispatchRuntimeAllocation(
            executor_url=executor_url,
            container_id=allocated_container_id,
        )

    async def cancel_runtime(self, session_id: str) -> None:
        await self.container_pool.cancel_task(session_id)
