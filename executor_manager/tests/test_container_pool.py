from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.container_pool import ContainerPool


def test_init_accepts_injected_runtime_adapters() -> None:
    docker_client = MagicMock()
    settings = SimpleNamespace()
    workspace_manager = MagicMock()

    with (
        patch(
            "app.services.container_pool.docker.from_env",
            side_effect=AssertionError("docker client should be injected"),
        ),
        patch(
            "app.services.container_pool.get_settings",
            side_effect=AssertionError("settings should be injected"),
        ),
        patch(
            "app.services.container_pool.WorkspaceManager",
            side_effect=AssertionError("workspace manager should be injected"),
        ),
    ):
        pool = ContainerPool(
            docker_client=docker_client,
            settings=settings,
            workspace_manager=workspace_manager,
        )

    assert pool.docker_client is docker_client
    assert pool.settings is settings
    assert pool.workspace_manager is workspace_manager


def test_wait_for_service_ready_uses_injected_health_client_factory() -> None:
    docker_client = MagicMock()
    settings = SimpleNamespace()
    workspace_manager = MagicMock()
    response = SimpleNamespace(status_code=200)
    client = MagicMock()
    client.get.return_value = response
    client_context = MagicMock()
    client_context.__enter__.return_value = client
    client_context.__exit__.return_value = None
    health_client_factory = MagicMock(return_value=client_context)

    pool = ContainerPool(
        docker_client=docker_client,
        settings=settings,
        workspace_manager=workspace_manager,
        health_client_factory=health_client_factory,
    )

    with patch(
        "app.services.container_pool.httpx.Client",
        side_effect=AssertionError("health client should be injected"),
    ):
        pool._wait_for_service_ready("http://executor", timeout=1)

    health_client_factory.assert_called_once_with()
    client.get.assert_called_once_with("http://executor/health")
