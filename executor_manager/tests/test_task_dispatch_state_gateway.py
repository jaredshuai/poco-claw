from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.task_dispatch_state_gateway import BackendTaskDispatchStateGateway


def test_backend_task_dispatch_state_gateway_backend_client_annotation_is_port() -> (
    None
):
    """BackendTaskDispatchStateGateway.__init__ backend_client must be typed as a Port/Protocol, not Any."""
    import inspect
    from typing import Any

    from app.services.task_dispatch_state_gateway import BackendClientPort

    sig = inspect.signature(BackendTaskDispatchStateGateway.__init__)
    param = sig.parameters["backend_client"]
    annotation = param.annotation

    # Assert annotation is BackendClientPort (a named Protocol), not Any or str
    assert annotation is not Any, "backend_client annotation must not be Any"
    assert annotation is BackendClientPort, (
        "backend_client annotation must be BackendClientPort"
    )


@pytest.mark.asyncio
async def test_backend_task_dispatch_state_gateway_marks_session_states() -> None:
    backend_client = MagicMock()
    backend_client.update_session_status = AsyncMock()
    gateway = BackendTaskDispatchStateGateway(backend_client)

    await gateway.mark_running(session_id="session-1")
    await gateway.mark_failed(session_id="session-1")

    backend_client.update_session_status.assert_any_await("session-1", "running")
    backend_client.update_session_status.assert_any_await("session-1", "failed")
