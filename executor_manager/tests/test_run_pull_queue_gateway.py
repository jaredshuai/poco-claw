import types
import typing
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_claim import RunDispatchClaim
from app.services.run_pull_queue_gateway import (
    BackendRunPullQueueGateway,
    RunPullQueueBackendClient,
)


def test_run_pull_queue_backend_client_claim_run_return_is_dispatch_claim_or_none() -> (
    None
):
    """Regression: claim_run return should be RunDispatchClaim | None, not raw backend payload."""
    hints = typing.get_type_hints(RunPullQueueBackendClient.claim_run)
    return_type = hints.get("return")

    origin = typing.get_origin(return_type)
    args = typing.get_args(return_type)

    assert origin is typing.Union or origin is types.UnionType, (
        f"Expected Union, got {origin}"
    )
    assert RunDispatchClaim in args
    assert type(None) in args
    assert "Any" not in str(return_type)
    assert "Mapping" not in str(return_type)
    assert "dict" not in str(return_type)


@pytest.mark.asyncio
async def test_backend_queue_gateway_forwards_typed_claim() -> None:
    claim = RunDispatchClaim(
        run_id=123,
        session_id="sess-1",
        user_id="user-1",
        prompt="do work",
        config_snapshot={"container_mode": "persistent"},
    )
    backend_client = MagicMock()
    backend_client.claim_run = AsyncMock(return_value=claim)
    gateway = BackendRunPullQueueGateway(backend_client)

    result = await gateway.claim_run(
        worker_id="worker-1",
        lease_seconds=30,
        schedule_modes=["manual"],
    )

    assert result is claim
    backend_client.claim_run.assert_awaited_once_with(
        worker_id="worker-1",
        lease_seconds=30,
        schedule_modes=["manual"],
    )


@pytest.mark.asyncio
async def test_backend_queue_gateway_rejects_raw_claim_payload() -> None:
    backend_client = MagicMock()
    backend_client.claim_run = AsyncMock(
        return_value={
            "run": {"run_id": "run-1", "session_id": "sess-1"},
            "user_id": "user-1",
            "prompt": "do work",
        }
    )
    gateway = BackendRunPullQueueGateway(backend_client)

    with pytest.raises(TypeError, match="requires RunDispatchClaim"):
        await gateway.claim_run(
            worker_id="worker-1",
            lease_seconds=30,
            schedule_modes=None,
        )
