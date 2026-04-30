from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.task_dispatch_state_gateway import BackendTaskDispatchStateGateway


@pytest.mark.asyncio
async def test_backend_task_dispatch_state_gateway_marks_session_states() -> None:
    backend_client = MagicMock()
    backend_client.update_session_status = AsyncMock()
    gateway = BackendTaskDispatchStateGateway(backend_client)

    await gateway.mark_running(session_id="session-1")
    await gateway.mark_failed(session_id="session-1")

    backend_client.update_session_status.assert_any_await("session-1", "running")
    backend_client.update_session_status.assert_any_await("session-1", "failed")
