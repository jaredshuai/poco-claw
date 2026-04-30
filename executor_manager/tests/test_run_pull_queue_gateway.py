from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_claim import RunDispatchClaim
from app.services.run_pull_queue_gateway import BackendRunPullQueueGateway


@pytest.mark.asyncio
async def test_backend_queue_gateway_normalizes_claim_payload() -> None:
    backend_client = MagicMock()
    backend_client.claim_run = AsyncMock(
        return_value={
            "run": {"run_id": 123, "session_id": "sess-1"},
            "user_id": "user-1",
            "prompt": "do work",
            "config_snapshot": {"container_mode": "persistent"},
        }
    )
    gateway = BackendRunPullQueueGateway(backend_client)

    claim = await gateway.claim_run(
        worker_id="worker-1",
        lease_seconds=30,
        schedule_modes=["manual"],
    )

    assert isinstance(claim, RunDispatchClaim)
    assert claim.run_id == 123
    assert claim.run_id_str == "123"
    assert claim.session_id == "sess-1"
    assert claim.user_id == "user-1"
    assert claim.prompt == "do work"
    assert claim.config_snapshot == {"container_mode": "persistent"}
    backend_client.claim_run.assert_awaited_once_with(
        worker_id="worker-1",
        lease_seconds=30,
        schedule_modes=["manual"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"run": {"session_id": "sess-1"}, "user_id": "user-1", "prompt": "do work"},
        {"run": {"run_id": "run-1"}, "user_id": "user-1", "prompt": "do work"},
        {"run": {"run_id": "run-1", "session_id": "sess-1"}, "prompt": "do work"},
        {"run": {"run_id": "run-1", "session_id": "sess-1"}, "user_id": "user-1"},
    ],
)
async def test_backend_queue_gateway_returns_none_for_invalid_claim_payload(
    payload: dict,
) -> None:
    backend_client = MagicMock()
    backend_client.claim_run = AsyncMock(return_value=payload)
    gateway = BackendRunPullQueueGateway(backend_client)

    claim = await gateway.claim_run(
        worker_id="worker-1",
        lease_seconds=30,
        schedule_modes=None,
    )

    assert claim is None
