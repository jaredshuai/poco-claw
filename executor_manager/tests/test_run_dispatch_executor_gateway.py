from unittest.mock import AsyncMock, MagicMock
import typing

import pytest

from app.services.run_dispatch_executor_gateway import (
    ExecutorClientRunDispatchGateway,
    RunDispatchExecutorClientPort,
    RunDispatchExecutorGateway,
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


def test_executor_client_gateway_constructor_uses_port_type() -> None:
    """Assert ExecutorClientRunDispatchGateway.__init__ executor_client annotation is the named Protocol."""
    sig = typing.get_type_hints(ExecutorClientRunDispatchGateway.__init__)

    executor_client_hint = sig.get("executor_client")
    assert executor_client_hint is not None
    hint_str = str(executor_client_hint)
    assert "Any" not in hint_str, "executor_client should not use Any"
    assert "RunDispatchExecutorClientPort" in hint_str, (
        "executor_client should use RunDispatchExecutorClientPort"
    )


def test_run_dispatch_executor_gateway_protocol_requires_str_run_id() -> None:
    """Assert RunDispatchExecutorGateway.execute_run requires run_id: str (not str | None)."""
    sig = typing.get_type_hints(RunDispatchExecutorGateway.execute_run)
    run_id_hint = sig.get("run_id")
    assert run_id_hint is not None
    hint_str = str(run_id_hint)
    assert "str" in hint_str
    assert "None" not in hint_str, "run_id should be str, not str | None"


def test_executor_client_run_dispatch_gateway_requires_str_run_id() -> None:
    """Assert ExecutorClientRunDispatchGateway.execute_run requires run_id: str (not str | None)."""
    sig = typing.get_type_hints(ExecutorClientRunDispatchGateway.execute_run)
    run_id_hint = sig.get("run_id")
    assert run_id_hint is not None
    hint_str = str(run_id_hint)
    assert "str" in hint_str
    assert "None" not in hint_str, "run_id should be str, not str | None"


def test_run_dispatch_executor_client_port_allows_optional_run_id() -> None:
    """Assert RunDispatchExecutorClientPort.execute_task still allows run_id: str | None."""
    sig = typing.get_type_hints(RunDispatchExecutorClientPort.execute_task)
    run_id_hint = sig.get("run_id")
    assert run_id_hint is not None
    hint_str = str(run_id_hint)
    assert "str" in hint_str
    assert "None" in hint_str, "run_id should allow None for legacy compatibility"
