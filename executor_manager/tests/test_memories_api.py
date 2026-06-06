"""Tests for app/api/v1/memories.py."""

from collections.abc import Mapping
from contextlib import contextmanager
import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _assert_mapping_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    assert "dict" not in str(annotation)
    assert get_origin(annotation) is Mapping
    assert get_args(annotation) == (str, object)


def _assert_list_mapping_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    assert get_origin(annotation) is list
    (item_type,) = get_args(annotation)
    _assert_mapping_str_object(item_type)


def _assert_dict_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    assert get_origin(annotation) is dict
    assert get_args(annotation) == (str, object)


def _assert_optional_dict_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    union_args = get_args(annotation)
    assert type(None) in union_args
    dict_hint = next(arg for arg in union_args if get_origin(arg) is dict)
    assert get_args(dict_hint) == (str, object)


def _load_memories_module_from_source():
    module_name = "_memories_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "memories.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


@contextmanager
def _backend_override(app, mock_client):
    from app.api.v1 import memories

    app.dependency_overrides[memories.get_backend_client] = lambda: mock_client
    try:
        yield
    finally:
        app.dependency_overrides.pop(memories.get_backend_client, None)


def test_memories_module_import_does_not_initialize_backend_client() -> None:
    with patch(
        "app.services.backend_client.BackendClient",
        side_effect=AssertionError("backend client should be lazy"),
    ):
        module = _load_memories_module_from_source()

    assert module.create_memories is not None


def test_memories_routes_use_backend_dependency_override() -> None:
    from app.main import app

    mock_client = MagicMock()
    mock_client.list_memories = AsyncMock(
        return_value=[{"id": "mem-123", "content": "remember this"}]
    )

    with _backend_override(app, mock_client):
        with patch(
            "app.api.v1.memories.BackendClient",
            side_effect=AssertionError("route should use dependency override"),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/memories?session_id=session-123")

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "mem-123"
    mock_client.list_memories.assert_awaited_once_with(session_id="session-123")


def test_memories_backend_provider_has_no_mutable_global() -> None:
    from app.api.v1 import memories

    assert not hasattr(memories, "backend_client")


def test_memories_backend_client_protocol_ports_are_structured() -> None:
    """Regression: memory API backend port avoids Any and raw dict payloads."""
    import typing
    from app.api.v1.memories import MemoriesBackendClient

    mapping_methods = [
        "create_memory",
        "get_memory_create_job",
        "get_memory",
        "update_memory",
        "delete_memory",
        "delete_all_memories",
    ]
    list_methods = [
        "list_memories",
        "search_memories",
        "get_memory_history",
    ]

    for method_name in mapping_methods:
        hints = typing.get_type_hints(getattr(MemoriesBackendClient, method_name))
        _assert_mapping_str_object(hints.get("return"))

    for method_name in list_methods:
        hints = typing.get_type_hints(getattr(MemoriesBackendClient, method_name))
        _assert_list_mapping_str_object(hints.get("return"))

    for method_name in ("create_memory", "search_memories", "update_memory"):
        hints = typing.get_type_hints(getattr(MemoriesBackendClient, method_name))
        _assert_dict_str_object(hints.get("payload"))


def test_memory_schema_payload_fields_do_not_expose_any() -> None:
    """Regression: memory DTO payload fields should use object, not Any."""
    from app.schemas.memory import (
        MemoryCreateJobResponse,
        MemoryCreateRequest,
        MemorySearchRequest,
        MemoryUpdateRequest,
    )

    create_hints = get_type_hints(MemoryCreateRequest)
    search_hints = get_type_hints(MemorySearchRequest)
    update_hints = get_type_hints(MemoryUpdateRequest)
    job_hints = get_type_hints(MemoryCreateJobResponse)

    _assert_optional_dict_str_object(create_hints["metadata"])
    _assert_optional_dict_str_object(search_hints["filters"])
    _assert_optional_dict_str_object(update_hints["metadata"])

    result_hint = job_hints["result"]
    result_args = get_args(result_hint)
    assert type(None) in result_args
    assert object in result_args
    assert Any not in result_args
    assert "Any" not in str(result_hint)


class TestMemoriesEndpoints(unittest.TestCase):
    """Test /api/v1/memories endpoints."""

    def test_create_memories_success(self) -> None:
        """Test successful memory creation."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.create_memory = AsyncMock(
            return_value={"job_id": "job-123", "status": "queued"}
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.post(
                "/api/v1/memories",
                json={
                    "session_id": "session-123",
                    "messages": [{"role": "user", "content": "test message"}],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["job_id"] == "job-123"
            mock_client.create_memory.assert_called_once()

    def test_get_memory_create_job_success(self) -> None:
        """Test successful memory create job retrieval."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.get_memory_create_job = AsyncMock(
            return_value={"job_id": "job-123", "status": "completed"}
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.get(
                "/api/v1/memories/jobs/job-123?session_id=session-123"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["job_id"] == "job-123"
            mock_client.get_memory_create_job.assert_called_once_with(
                session_id="session-123",
                job_id="job-123",
            )

    def test_list_memories_success(self) -> None:
        """Test successful memories listing."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.list_memories = AsyncMock(
            return_value=[
                {"id": "mem-1", "content": "memory 1"},
                {"id": "mem-2", "content": "memory 2"},
            ]
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.get("/api/v1/memories?session_id=session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]) == 2
            mock_client.list_memories.assert_called_once_with(session_id="session-123")

    def test_search_memories_success(self) -> None:
        """Test successful memories search."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.search_memories = AsyncMock(
            return_value=[{"id": "mem-1", "content": "matched memory"}]
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.post(
                "/api/v1/memories/search",
                json={
                    "session_id": "session-123",
                    "query": "test query",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]) == 1
            mock_client.search_memories.assert_called_once()

    def test_get_memory_success(self) -> None:
        """Test successful single memory retrieval."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.get_memory = AsyncMock(
            return_value={"id": "mem-123", "content": "test memory"}
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.get("/api/v1/memories/mem-123?session_id=session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["id"] == "mem-123"
            mock_client.get_memory.assert_called_once_with(
                session_id="session-123",
                memory_id="mem-123",
            )

    def test_update_memory_success(self) -> None:
        """Test successful memory update."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.update_memory = AsyncMock(
            return_value={"id": "mem-123", "content": "updated content"}
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.put(
                "/api/v1/memories/mem-123",
                json={
                    "session_id": "session-123",
                    "text": "updated memory text",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            mock_client.update_memory.assert_called_once()

    def test_get_memory_history_success(self) -> None:
        """Test successful memory history retrieval."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.get_memory_history = AsyncMock(
            return_value=[
                {"version": 1, "content": "old"},
                {"version": 2, "content": "new"},
            ]
        )

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.get(
                "/api/v1/memories/mem-123/history?session_id=session-123"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]) == 2
            mock_client.get_memory_history.assert_called_once_with(
                session_id="session-123",
                memory_id="mem-123",
            )

    def test_delete_memory_success(self) -> None:
        """Test successful memory deletion."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.delete_memory = AsyncMock(return_value={"deleted": True})

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.delete("/api/v1/memories/mem-123?session_id=session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            mock_client.delete_memory.assert_called_once_with(
                session_id="session-123",
                memory_id="mem-123",
            )

    def test_delete_all_memories_success(self) -> None:
        """Test successful deletion of all memories."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.delete_all_memories = AsyncMock(return_value={"deleted_count": 5})

        with _backend_override(app, mock_client):
            client = TestClient(app)
            response = client.delete("/api/v1/memories?session_id=session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            mock_client.delete_all_memories.assert_called_once_with(
                session_id="session-123"
            )


if __name__ == "__main__":
    unittest.main()
