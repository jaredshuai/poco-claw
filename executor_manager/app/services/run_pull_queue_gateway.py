from typing import Any, Protocol


class RunPullQueueGateway(Protocol):
    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> dict[str, Any] | None: ...


class BackendRunPullQueueGateway:
    def __init__(self, backend_client: Any) -> None:
        self.backend_client = backend_client

    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> dict[str, Any] | None:
        return await self.backend_client.claim_run(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            schedule_modes=schedule_modes,
        )
