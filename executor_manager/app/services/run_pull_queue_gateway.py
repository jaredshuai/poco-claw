from typing import Protocol

from app.services.run_dispatch_claim import RunDispatchClaim


class RunPullQueueGateway(Protocol):
    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> RunDispatchClaim | None: ...


class RunPullQueueBackendClient(Protocol):
    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> RunDispatchClaim | None: ...


class BackendRunPullQueueGateway:
    def __init__(self, backend_client: RunPullQueueBackendClient) -> None:
        self.backend_client = backend_client

    async def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None,
    ) -> RunDispatchClaim | None:
        claim = await self.backend_client.claim_run(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            schedule_modes=schedule_modes,
        )
        if claim is None:
            return None
        if not isinstance(claim, RunDispatchClaim):
            raise TypeError(
                "BackendRunPullQueueGateway.claim_run requires RunDispatchClaim"
            )
        return claim
