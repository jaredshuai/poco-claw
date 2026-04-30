from typing import Any, Protocol


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
