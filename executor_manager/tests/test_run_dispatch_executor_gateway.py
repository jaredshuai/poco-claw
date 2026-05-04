from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_executor_gateway import (
    ExecutorClientRunDispatchGateway,
)
from app.services.run_dispatch_execution_context import RunDispatchExecutionContext


@pytest.mark.asyncio
async def test_executor_client_gateway_executes_run_through_executor_client() -> None:
    executor_client = MagicMock()
    executor_client.execute_task = AsyncMock(return_value="sdk-session-1")
    gateway = ExecutorClientRunDispatchGateway(executor_client)

    result = await gateway.execute_run(
        executor_url="http://executor.local",
        session_id="sess-1",
        run_id="run-1",
        prompt="do work",
        execution_context=RunDispatchExecutionContext(
            callback_base_url="http://manager.local",
            callback_url="http://manager.local/api/v1/callback",
            callback_token="callback-token",
            task_lease_secret="lease-secret",
            running_lease_seconds=3600,
        ),
        config={"skill_files": {}, "plugin_files": {}, "input_files": []},
        sdk_session_id="sdk-session-0",
        permission_mode="acceptEdits",
    )

    assert result == "sdk-session-1"
    executor_client.execute_task.assert_awaited_once_with(
        executor_url="http://executor.local",
        session_id="sess-1",
        run_id="run-1",
        prompt="do work",
        callback_url="http://manager.local/api/v1/callback",
        callback_token="callback-token",
        task_lease_secret="lease-secret",
        config={"skill_files": {}, "plugin_files": {}, "input_files": []},
        callback_base_url="http://manager.local",
        sdk_session_id="sdk-session-0",
        permission_mode="acceptEdits",
    )
