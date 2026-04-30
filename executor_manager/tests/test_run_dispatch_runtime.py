from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_dispatch_runtime import ContainerPoolRunDispatchRuntime


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

    assert result == ("http://executor.local", "container-1")
    container_pool.get_or_create_container.assert_awaited_once_with(
        session_id="sess-1",
        user_id="user-1",
        browser_enabled=True,
        container_mode="persistent",
        container_id="existing-container",
    )


@pytest.mark.asyncio
async def test_container_pool_runtime_cancels_by_session_id() -> None:
    container_pool = MagicMock()
    container_pool.cancel_task = AsyncMock()
    runtime = ContainerPoolRunDispatchRuntime(container_pool)

    await runtime.cancel_runtime("sess-1")

    container_pool.cancel_task.assert_awaited_once_with("sess-1")
