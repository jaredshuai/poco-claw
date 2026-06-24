"""Tests for the ComputerProvider port and the DockerComputerProvider adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.computer_provider import (
    ComputerCapability,
    ComputerInstance,
    ComputerProvider,
)
from app.services.docker_computer_provider import DockerComputerProvider


# ---------------------------------------------------------------------------
# DockerComputerProvider.acquire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_docker_provider_acquire_maps_browser_capability() -> None:
    """BROWSER in requires → browser_enabled=True passed to pool."""
    pool = MagicMock()
    pool.get_or_create_container = AsyncMock(
        return_value=("http://localhost:9001", "exec-abc12345")
    )
    provider = DockerComputerProvider(pool)

    instance = await provider.acquire(
        session_id="sess-1",
        user_id="user-1",
        requires={ComputerCapability.SHELL, ComputerCapability.BROWSER},
        reuse_id="existing-container",
    )

    assert isinstance(instance, ComputerInstance)
    assert instance.executor_endpoint == "http://localhost:9001"
    assert instance.instance_id == "exec-abc12345"
    assert instance.provider == "docker"
    assert ComputerCapability.SHELL in instance.capabilities
    assert ComputerCapability.FILESYSTEM in instance.capabilities
    assert ComputerCapability.BROWSER in instance.capabilities

    pool.get_or_create_container.assert_awaited_once_with(
        session_id="sess-1",
        user_id="user-1",
        browser_enabled=True,
        container_mode="ephemeral",
        container_id="existing-container",
    )


@pytest.mark.asyncio
async def test_docker_provider_acquire_passes_mode_through() -> None:
    """mode='persistent' is forwarded to the pool as container_mode."""
    pool = MagicMock()
    pool.get_or_create_container = AsyncMock(
        return_value=("http://localhost:9003", "exec-persist1")
    )
    provider = DockerComputerProvider(pool)

    await provider.acquire(
        session_id="sess-3",
        user_id="user-3",
        requires={ComputerCapability.SHELL},
        mode="persistent",
    )

    call_kwargs = pool.get_or_create_container.await_args.kwargs
    assert call_kwargs["container_mode"] == "persistent"


@pytest.mark.asyncio
async def test_docker_provider_acquire_without_browser() -> None:
    """No BROWSER capability → browser_enabled=False, caps lack BROWSER."""
    pool = MagicMock()
    pool.get_or_create_container = AsyncMock(
        return_value=("http://localhost:9002", "exec-def67890")
    )
    provider = DockerComputerProvider(pool)

    instance = await provider.acquire(
        session_id="sess-2",
        user_id="user-2",
        requires={ComputerCapability.SHELL},
    )

    assert ComputerCapability.BROWSER not in instance.capabilities
    assert ComputerCapability.SHELL in instance.capabilities

    call_kwargs = pool.get_or_create_container.await_args.kwargs
    assert call_kwargs["browser_enabled"] is False
    assert call_kwargs["container_id"] is None


# ---------------------------------------------------------------------------
# DockerComputerProvider.release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_docker_provider_release_delegates_to_cancel_task() -> None:
    pool = MagicMock()
    pool.cancel_task = AsyncMock()
    provider = DockerComputerProvider(pool)

    await provider.release("sess-1")

    pool.cancel_task.assert_awaited_once_with("sess-1")


# ---------------------------------------------------------------------------
# ComputerProvider protocol structure (static checks)
# ---------------------------------------------------------------------------


def test_computer_provider_protocol_has_acquire_and_release() -> None:
    """The protocol surface must expose acquire + release."""
    import typing

    assert hasattr(ComputerProvider, "acquire")
    assert hasattr(ComputerProvider, "release")

    acquire_hints = typing.get_type_hints(ComputerProvider.acquire)
    assert acquire_hints["return"] is ComputerInstance
