"""Tests for app/api/v1/user_input_requests.py."""

from contextlib import contextmanager
import importlib.util
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import get_args, get_origin
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _load_user_input_requests_module_from_source():
    module_name = "_user_input_requests_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "user_input_requests.py"
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
    from app.api.v1 import user_input_requests

    app.dependency_overrides[user_input_requests.get_backend_client] = lambda: (
        mock_client
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(user_input_requests.get_backend_client, None)


def test_user_input_requests_module_import_does_not_initialize_backend_client() -> None:
    with patch(
        "app.services.backend_client.BackendClient",
        side_effect=AssertionError("backend client should be lazy"),
    ):
        module = _load_user_input_requests_module_from_source()

    assert module.create_user_input_request is not None


def test_user_input_requests_routes_use_backend_dependency_override() -> None:
    from app.api.v1 import user_input_requests
    from app.main import app

    if hasattr(user_input_requests, "backend_client"):
        user_input_requests.backend_client = None

    mock_client = MagicMock()
    mock_client.get_user_input_request = AsyncMock(
        return_value={"request_id": "req-123", "status": "completed"}
    )

    app.dependency_overrides[user_input_requests.get_backend_client] = lambda: (
        mock_client
    )
    try:
        with (
            patch(
                "app.api.v1.user_input_requests.BackendClient",
                side_effect=AssertionError("route should use dependency override"),
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/v1/user-input-requests/req-123",
                headers={"Authorization": "Bearer callback-token"},
            )
    finally:
        app.dependency_overrides.pop(user_input_requests.get_backend_client, None)

    assert response.status_code == 200
    assert response.json()["data"]["request_id"] == "req-123"
    mock_client.get_user_input_request.assert_awaited_once_with("req-123")


def test_user_input_requests_backend_provider_has_no_mutable_global() -> None:
    from app.api.v1 import user_input_requests

    assert not hasattr(user_input_requests, "backend_client")


def _assert_mapping_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    assert "dict" not in str(annotation)
    assert get_origin(annotation) is Mapping
    assert get_args(annotation) == (str, object)


def test_user_input_requests_backend_client_protocol_is_structured() -> None:
    """Regression: route backend port avoids Any and bare dict."""
    import typing
    from app.api.v1.user_input_requests import UserInputRequestsBackendClient

    create_hints = typing.get_type_hints(
        UserInputRequestsBackendClient.create_user_input_request
    )
    get_hints = typing.get_type_hints(
        UserInputRequestsBackendClient.get_user_input_request
    )

    payload_hint = create_hints.get("payload")
    assert payload_hint is not None
    assert "Any" not in str(payload_hint)
    assert get_origin(payload_hint) is dict
    assert get_args(payload_hint) == (str, object)

    _assert_mapping_str_object(create_hints.get("return"))

    return_hint = get_hints.get("return")
    assert return_hint is not None
    assert "Any" not in str(return_hint)
    assert "dict" not in str(return_hint)
    args = get_args(return_hint)
    mapping_type = next(
        (arg for arg in args if get_origin(arg) is Mapping),
        None,
    )
    assert mapping_type is not None
    assert get_args(mapping_type) == (str, object)


class TestUserInputRequestsEndpoints(unittest.TestCase):
    """Test /api/v1/user-input-requests endpoints."""

    def test_create_user_input_request_requires_callback_token(self) -> None:
        """Test user input request creation rejects missing callback token."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.create_user_input_request = AsyncMock(
            return_value={"id": "req-123", "status": "pending"}
        )

        with (
            _backend_override(app, mock_client),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/user-input-requests",
                json={
                    "session_id": "session-123",
                    "tool_name": "ask_user",
                    "tool_input": {"question": "What is the capital of France?"},
                },
            )

        assert response.status_code == 403
        mock_client.create_user_input_request.assert_not_called()

    def test_get_user_input_request_requires_callback_token(self) -> None:
        """Test user input request retrieval rejects missing callback token."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.get_user_input_request = AsyncMock(
            return_value={"request_id": "req-123", "status": "completed"}
        )

        with (
            _backend_override(app, mock_client),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/user-input-requests/req-123")

        assert response.status_code == 403
        mock_client.get_user_input_request.assert_not_called()

    def test_create_user_input_request_success(self) -> None:
        """Test successful user input request creation."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.create_user_input_request = AsyncMock(
            return_value={"id": "req-123", "status": "pending"}
        )

        with (
            _backend_override(app, mock_client),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/user-input-requests",
                json={
                    "session_id": "session-123",
                    "tool_name": "ask_user",
                    "tool_input": {"question": "What is the capital of France?"},
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["id"] == "req-123"
            mock_client.create_user_input_request.assert_called_once()

    def test_create_user_input_request_with_expires_at(self) -> None:
        """Test user input request creation with expires_at."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.create_user_input_request = AsyncMock(
            return_value={"id": "req-456", "status": "pending"}
        )

        with (
            _backend_override(app, mock_client),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/user-input-requests",
                json={
                    "session_id": "session-456",
                    "tool_name": "ask_user",
                    "tool_input": {"question": "Test prompt"},
                    "expires_at": "2026-04-01T00:00:00Z",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["id"] == "req-456"

    def test_get_user_input_request_success(self) -> None:
        """Test successful user input request retrieval."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.get_user_input_request = AsyncMock(
            return_value={
                "request_id": "req-123",
                "status": "completed",
                "response": "Paris",
            }
        )

        with (
            _backend_override(app, mock_client),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app)
            response = client.get(
                "/api/v1/user-input-requests/req-123",
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["request_id"] == "req-123"
            mock_client.get_user_input_request.assert_called_once_with("req-123")

    def test_get_user_input_request_not_found(self) -> None:
        """Test user input request not found."""
        from app.main import app

        mock_client = MagicMock()
        mock_client.get_user_input_request = AsyncMock(return_value=None)

        with (
            _backend_override(app, mock_client),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app)
            response = client.get(
                "/api/v1/user-input-requests/nonexistent",
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0


if __name__ == "__main__":
    unittest.main()
