from unittest.mock import AsyncMock, MagicMock

import pytest
import types
import typing
from collections.abc import Mapping

from app.services.run_dispatch_claim import RunDispatchClaim
from app.services.run_pull_queue_gateway import (
    BackendRunPullQueueGateway,
    RunPullQueueBackendClient,
)


def test_run_pull_queue_backend_client_claim_run_return_is_mapping_str_object_or_none() -> (
    None
):
    """Regression: claim_run return should be Mapping[str, object] | None, not Mapping[str, Any] | None."""
    hints = typing.get_type_hints(RunPullQueueBackendClient.claim_run)
    return_type = hints.get("return")

    # Extract the type inside Optional (Union with None)
    origin = typing.get_origin(return_type)
    args = typing.get_args(return_type)

    # Should be Union[Mapping[str, object], None] - but in Python 3.12+ it's types.UnionType
    assert origin is typing.Union or origin is types.UnionType, (
        f"Expected Union, got {origin}"
    )

    # Find the Mapping type in the Union args
    mapping_type = None
    for arg in args:
        origin_arg = typing.get_origin(arg)
        if origin_arg is Mapping:
            mapping_type = arg
            break

    assert mapping_type is not None, "Expected Mapping in Union"

    # Verify the Mapping is Mapping[str, object], not Mapping[str, Any]
    mapping_args = typing.get_args(mapping_type)
    assert mapping_args[0] is str, f"Expected str key, got {mapping_args[0]}"
    assert mapping_args[1] is object, f"Expected object value, got {mapping_args[1]}"


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
