from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_runtime import ContainerPoolRunDispatchRuntime
from app.services.run_dispatch_runtime import RunDispatchRuntime
from app.services.run_dispatch_runtime import RunDispatchRuntimeAllocation


@pytest.mark.asyncio
async def test_container_pool_runtime_allocates_executor_target() -> None:
    container_pool = MagicMock()
    container_pool.get_or_create_container = AsyncMock(
        return_value=("http://executor.local", "container-1")
    )
    runtime = ContainerPoolRunDispatchRuntime(container_pool)

    result = await runtime.allocate_runtime(
        session_id="sess-1",
        user_id="user-1",
        browser_enabled=True,
        container_mode="persistent",
        container_id="existing-container",
    )

    assert result == RunDispatchRuntimeAllocation(
        executor_url="http://executor.local",
        container_id="container-1",
    )
    container_pool.get_or_create_container.assert_awaited_once_with(
        session_id="sess-1",
        user_id="user-1",
        browser_enabled=True,
        container_mode="persistent",
        container_id="existing-container",
    )


def test_run_dispatch_runtime_allocate_runtime_returns_named_allocation() -> None:
    """Regression: runtime allocation should be named, not a raw tuple."""
    import typing

    hints = typing.get_type_hints(RunDispatchRuntime.allocate_runtime)
    return_type = hints.get("return")

    assert return_type is RunDispatchRuntimeAllocation
    assert "tuple" not in str(return_type)
    assert "Any" not in str(return_type)


@pytest.mark.asyncio
async def test_container_pool_runtime_cancels_by_session_id() -> None:
    container_pool = MagicMock()
    container_pool.cancel_task = AsyncMock()
    runtime = ContainerPoolRunDispatchRuntime(container_pool)

    await runtime.cancel_runtime("sess-1")

    container_pool.cancel_task.assert_awaited_once_with("sess-1")
