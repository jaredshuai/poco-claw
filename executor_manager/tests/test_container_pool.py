from collections.abc import Callable
from types import SimpleNamespace, UnionType
from typing import get_type_hints, get_origin, get_args, Union
from unittest.mock import MagicMock, patch

from app.services.container_pool import (
    ContainerPool,
    DockerClientProtocol,
    DockerContainer,
    DockerContainersAPI,
    DockerImagesAPI,
    build_container_docker_client,
)
from app.schemas.task import ContainerInfoResponse, ContainerStatsResponse


def test_init_with_defaults_defers_runtime_adapter_construction() -> None:
    settings = SimpleNamespace()
    docker_client = MagicMock()
    workspace_manager = MagicMock()

    with (
        patch(
            "app.services.container_pool.docker.from_env",
            return_value=docker_client,
        ) as docker_client_factory,
        patch(
            "app.services.container_pool.WorkspaceManager",
            return_value=workspace_manager,
        ) as workspace_manager_factory,
    ):
        pool = ContainerPool(settings=settings)

        docker_client_factory.assert_not_called()
        workspace_manager_factory.assert_not_called()

        assert pool.docker_client is docker_client
        assert pool.workspace_manager is workspace_manager

    docker_client_factory.assert_called_once_with()
    workspace_manager_factory.assert_called_once_with()


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


def test_init_uses_injected_docker_client_factory_without_default_constructor() -> None:
    docker_client = MagicMock()
    settings = SimpleNamespace()
    workspace_manager = MagicMock()

    with patch(
        "app.services.container_pool.docker.from_env",
        side_effect=AssertionError("docker client should be injected"),
    ):
        pool = ContainerPool(
            docker_client_factory=lambda: docker_client,
            settings=settings,
            workspace_manager=workspace_manager,
        )

    assert pool.docker_client is docker_client


def test_init_uses_injected_workspace_manager_factory_without_default_constructor() -> (
    None
):
    docker_client = MagicMock()
    settings = SimpleNamespace()
    workspace_manager = MagicMock()

    with patch(
        "app.services.container_pool.WorkspaceManager",
        side_effect=AssertionError("workspace manager should be injected"),
    ):
        pool = ContainerPool(
            docker_client=docker_client,
            settings=settings,
            workspace_manager_factory=lambda: workspace_manager,
        )

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


def test_build_container_docker_client_return_annotation_uses_docker_client_protocol() -> (
    None
):
    """Verify build_container_docker_client return annotation uses DockerClientProtocol."""
    hints = get_type_hints(build_container_docker_client, include_extras=True)
    return_hint = hints.get("return")
    assert return_hint is not None
    # Handle PEP 604 union (X | Y) and Optional[X]
    origin = get_origin(return_hint)
    if origin is Union or isinstance(return_hint, UnionType):
        # PEP 604: X | Y, or Union[X, Y]
        args = get_args(return_hint)
        # Get the non-None type
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            actual_type = non_none_types[0]
        else:
            actual_type = return_hint
    elif hasattr(return_hint, "__args__"):
        # Optional[X] case
        args = return_hint.__args__
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            actual_type = non_none_types[0]
        else:
            actual_type = return_hint
    else:
        actual_type = return_hint
    assert actual_type is DockerClientProtocol, (
        f"Expected DockerClientProtocol, got {actual_type}"
    )


def test_container_pool_init_docker_client_annotation_uses_docker_client_protocol() -> (
    None
):
    """Verify ContainerPool.__init__ docker_client annotation uses DockerClientProtocol."""
    hints = get_type_hints(ContainerPool.__init__, include_extras=True)
    docker_client_hint = hints.get("docker_client")
    assert docker_client_hint is not None
    # docker_client: DockerClientProtocol | None
    # Check if it's a Union/Optional (PEP 604 or Optional)
    origin = get_origin(docker_client_hint)
    if origin is Union or isinstance(docker_client_hint, UnionType):
        # PEP 604: X | Y, or Union[X, Y]
        args = get_args(docker_client_hint)
        non_none_types = [t for t in args if t is not type(None)]
        assert len(non_none_types) == 1
        actual_type = non_none_types[0]
    elif hasattr(docker_client_hint, "__args__"):
        # Optional[X] case
        args = docker_client_hint.__args__
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            actual_type = non_none_types[0]
        else:
            actual_type = docker_client_hint
    else:
        actual_type = docker_client_hint
    assert actual_type is DockerClientProtocol, (
        f"Expected DockerClientProtocol, got {actual_type}"
    )


def test_container_pool_init_docker_client_factory_annotation_contains_docker_client_protocol() -> (
    None
):
    """Verify ContainerPool.__init__ docker_client_factory annotation contains DockerClientProtocol."""
    hints = get_type_hints(ContainerPool.__init__, include_extras=True)
    factory_hint = hints.get("docker_client_factory")
    assert factory_hint is not None
    # docker_client_factory: Callable[[], DockerClientProtocol] | None
    # Check return annotation of the callable
    origin = get_origin(factory_hint)
    if origin is Union or isinstance(factory_hint, UnionType):
        # PEP 604: X | Y, or Union[X, Y]
        args = get_args(factory_hint)
        non_none_types = [t for t in args if t is not type(None)]
        assert len(non_none_types) == 1
        callable_type = non_none_types[0]
    elif hasattr(factory_hint, "__args__"):
        # Optional[X] case
        args = factory_hint.__args__
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            callable_type = non_none_types[0]
        else:
            callable_type = factory_hint
    else:
        callable_type = factory_hint

    # Get the return type from Callable[[...], ReturnType]
    callable_origin = get_origin(callable_type)
    if callable_origin is Callable:
        callable_args = get_args(callable_type)
        if callable_args:
            return_type = callable_args[-1]
        else:
            return_type = None
    elif hasattr(callable_type, "__args__"):
        # Fallback to __args__
        callable_args = callable_type.__args__
        if callable_args:
            return_type = callable_args[-1]
        else:
            return_type = None
    else:
        # Maybe it's a ParamSpec generic, check __origin__
        return_type = getattr(callable_type, "return_type", None)
        if return_type is None and hasattr(callable_type, "__origin__"):
            # For Callable, the return is in __args__
            return_type = getattr(callable_type, "__args__", None)
            if return_type:
                return_type = return_type[-1]

    assert return_type is not None
    assert return_type is DockerClientProtocol, (
        f"Expected DockerClientProtocol, got {return_type}"
    )


def test_container_pool_docker_client_property_annotation_uses_docker_client_protocol() -> (
    None
):
    """Verify ContainerPool.docker_client property return annotation uses DockerClientProtocol."""
    # Get the property descriptor
    docker_client_prop = getattr(ContainerPool, "docker_client")
    assert hasattr(docker_client_prop, "fget"), "docker_client should be a property"
    getter = docker_client_prop.fget
    assert getter is not None
    hints = get_type_hints(getter, include_extras=True)
    return_hint = hints.get("return")
    assert return_hint is not None
    assert return_hint is DockerClientProtocol, (
        f"Expected DockerClientProtocol, got {return_hint}"
    )


def test_container_pool_docker_client_setter_value_annotation_uses_docker_client_protocol() -> (
    None
):
    """Verify ContainerPool.docker_client setter value annotation uses DockerClientProtocol."""
    docker_client_prop = getattr(ContainerPool, "docker_client")
    assert hasattr(docker_client_prop, "fset"), "docker_client should have a setter"
    setter = docker_client_prop.fset
    assert setter is not None
    hints = get_type_hints(setter, include_extras=True)
    # The setter takes 'value' as first param after self
    value_hint = hints.get("value")
    assert value_hint is not None
    assert value_hint is DockerClientProtocol, (
        f"Expected DockerClientProtocol, got {value_hint}"
    )


def test_container_pool_get_container_stats_returns_container_stats_response() -> None:
    """Verify container stats are returned as a typed response DTO."""
    pool = ContainerPool(
        docker_client=MagicMock(),
        settings=SimpleNamespace(),
        workspace_manager=MagicMock(),
    )
    pool.containers = {
        "container-1": SimpleNamespace(
            labels={
                "container_id": "container-1",
                "container_mode": "persistent",
            },
            name="executor-1",
            status="running",
        ),
        "container-2": SimpleNamespace(
            labels={
                "container_id": "container-2",
                "container_mode": "ephemeral",
            },
            name="executor-2",
            status="exited",
        ),
        "container-3": SimpleNamespace(
            labels={
                "container_id": 123,
                "container_mode": ["invalid"],
            },
            name="executor-3",
            status=None,
        ),
    }

    stats = pool.get_container_stats()

    assert isinstance(stats, ContainerStatsResponse)
    assert stats.total_active == 3
    assert stats.persistent_containers == 1
    assert stats.ephemeral_containers == 2
    assert stats.containers[0].container_id == "container-1"
    assert stats.containers[2].container_id == "executor-3"
    assert stats.containers[2].mode == "ephemeral"
    assert stats.containers[2].status == ""


def test_container_pool_get_container_stats_return_annotation_uses_response_dto() -> (
    None
):
    """Verify get_container_stats is typed as ContainerStatsResponse, not Any."""
    hints = get_type_hints(ContainerPool.get_container_stats)

    assert hints.get("return") is ContainerStatsResponse


def test_container_stats_response_containers_field_uses_container_info_dto() -> None:
    """Verify container stats do not expose raw dict entries."""
    field = ContainerStatsResponse.model_fields["containers"]

    assert field.annotation == list[ContainerInfoResponse]
    assert "dict" not in str(field.annotation)


def test_docker_containers_api_protocol_declares_required_members() -> None:
    """Verify DockerContainersAPI protocol declares required members."""
    # Check protocol has these method signatures defined
    annotations = getattr(DockerContainersAPI, "__annotations__", {})
    assert "get" in annotations or hasattr(DockerContainersAPI, "get")
    assert "run" in annotations or hasattr(DockerContainersAPI, "run")
    assert "list" in annotations or hasattr(DockerContainersAPI, "list")


def test_docker_containers_api_returns_docker_container_not_any() -> None:
    """Regression: Docker container API returns typed container protocol objects."""
    get_hints = get_type_hints(DockerContainersAPI.get)
    run_hints = get_type_hints(DockerContainersAPI.run)
    list_hints = get_type_hints(DockerContainersAPI.list)

    assert get_hints["return"] is DockerContainer
    assert run_hints["return"] is DockerContainer
    assert "Any" not in str(get_hints["return"])
    assert "Any" not in str(run_hints["return"])

    list_return_hint = list_hints["return"]
    assert get_origin(list_return_hint) is list
    assert get_args(list_return_hint) == (DockerContainer,)
    assert "Any" not in str(list_return_hint)


def test_docker_containers_api_payload_annotations_use_object_not_any() -> None:
    """Regression: Docker API payload values avoid Any at the port boundary."""
    run_hints = get_type_hints(DockerContainersAPI.run)
    list_hints = get_type_hints(DockerContainersAPI.list)

    assert run_hints["kwargs"] is object
    assert "Any" not in str(run_hints["kwargs"])

    filters_hint = list_hints["filters"]
    assert "Any" not in str(filters_hint)
    assert "dict[str, object]" in str(filters_hint)


def test_docker_container_protocol_declares_runtime_members() -> None:
    """Verify DockerContainer captures the runtime members ContainerPool needs."""
    annotations = getattr(DockerContainer, "__annotations__", {})

    for member in ("id", "labels", "name", "ports", "attrs", "status"):
        assert member in annotations
        assert "Any" not in str(annotations[member])

    for method_name in ("reload", "remove", "stop"):
        assert hasattr(DockerContainer, method_name)


def test_docker_images_api_protocol_declares_required_members() -> None:
    """Verify DockerImagesAPI protocol declares required members."""
    annotations = getattr(DockerImagesAPI, "__annotations__", {})
    assert "get" in annotations or hasattr(DockerImagesAPI, "get")


def test_docker_client_protocol_declares_required_members() -> None:
    """Verify DockerClientProtocol protocol declares required members."""
    annotations = getattr(DockerClientProtocol, "__annotations__", {})
    for member in ("containers", "images"):
        assert member in annotations or hasattr(DockerClientProtocol, member), (
            f"DockerClientProtocol missing member: {member}"
        )
