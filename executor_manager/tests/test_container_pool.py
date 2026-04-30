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
