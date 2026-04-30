from typing import Any, Protocol

from app.services.run_dispatch_claim import RunDispatchClaim


class RunPullQueueGateway(Protocol):
    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> RunDispatchClaim | None: ...


class BackendRunPullQueueGateway:
    def __init__(self, backend_client: Any) -> None:
        self.backend_client = backend_client

    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> RunDispatchClaim | None:
        payload = await self.backend_client.claim_run(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            schedule_modes=schedule_modes,
        )
        if not payload:
            return None
        return RunDispatchClaim.from_payload(payload)
