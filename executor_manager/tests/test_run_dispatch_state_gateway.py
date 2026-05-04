from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_state_gateway import BackendRunDispatchStateGateway


@pytest.mark.asyncio
async def test_backend_state_gateway_records_mcp_staged_servers_batch() -> None:
    backend_client = MagicMock()
    backend_client.record_mcp_transition = AsyncMock()
    gateway = BackendRunDispatchStateGateway(backend_client)

    await gateway.record_mcp_staged_servers(
        run_id="run-1",
        session_id="sess-1",
        server_names=["server-a", "server-b", "server-c"],
    )

    assert backend_client.record_mcp_transition.await_count == 3
    backend_client.record_mcp_transition.assert_any_await(
        run_id="run-1",
        session_id="sess-1",
        server_name="server-a",
        to_state="staged",
        event_source="executor_manager",
    )
    backend_client.record_mcp_transition.assert_any_await(
        run_id="run-1",
        session_id="sess-1",
        server_name="server-b",
        to_state="staged",
        event_source="executor_manager",
    )
    backend_client.record_mcp_transition.assert_any_await(
        run_id="run-1",
        session_id="sess-1",
        server_name="server-c",
        to_state="staged",
        event_source="executor_manager",
    )


@pytest.mark.asyncio
async def test_backend_state_gateway_batch_records_all_servers_despite_failures() -> (
    None
):
    backend_client = MagicMock()
    call_count = 0

    async def failing_transition(**kwargs) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("transient failure")

    backend_client.record_mcp_transition = AsyncMock(side_effect=failing_transition)
    gateway = BackendRunDispatchStateGateway(backend_client)

    await gateway.record_mcp_staged_servers(
        run_id="run-1",
        session_id="sess-1",
        server_names=["server-a", "server-b", "server-c"],
    )

    assert call_count == 3


@pytest.mark.asyncio
async def test_backend_state_gateway_starts_and_fails_run() -> None:
    backend_client = MagicMock()
    backend_client.start_run = AsyncMock()
    backend_client.fail_run = AsyncMock()
    gateway = BackendRunDispatchStateGateway(backend_client)

    await gateway.start_run(run_id="run-1", worker_id="worker-1")
    await gateway.fail_run(
        run_id="run-1",
        worker_id="worker-1",
        error_message="dispatch failed",
    )

    backend_client.start_run.assert_awaited_once_with(
        run_id="run-1",
        worker_id="worker-1",
        lease_seconds=None,
    )
    backend_client.fail_run.assert_awaited_once_with(
        run_id="run-1",
        worker_id="worker-1",
        error_message="dispatch failed",
    )


@pytest.mark.asyncio
async def test_backend_state_gateway_start_run_passes_lease_seconds() -> None:
    backend_client = MagicMock()
    backend_client.start_run = AsyncMock()
    gateway = BackendRunDispatchStateGateway(backend_client)

    await gateway.start_run(run_id="run-1", worker_id="worker-1", lease_seconds=3600)

    backend_client.start_run.assert_awaited_once_with(
        run_id="run-1",
        worker_id="worker-1",
        lease_seconds=3600,
    )
