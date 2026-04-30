"""Tests for app/api/v1 endpoints via TestClient."""

from contextlib import contextmanager
import io
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _load_callback_module_from_source():
    module_name = "_callback_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "callback.py"
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


def _load_computer_module_from_source():
    module_name = "_computer_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "computer.py"
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
def _callback_service_override(app, mock_service):
    from app.api.v1 import callback

    app.dependency_overrides[callback.get_callback_service] = lambda: mock_service
    try:
        yield
    finally:
        app.dependency_overrides.pop(callback.get_callback_service, None)


@contextmanager
def _computer_service_override(app, mock_service):
    from app.api.v1 import computer

    app.dependency_overrides[computer.get_computer_service] = lambda: mock_service
    try:
        yield
    finally:
        app.dependency_overrides.pop(computer.get_computer_service, None)


def test_callback_module_import_does_not_initialize_service() -> None:
    with patch(
        "app.services.callback_service.CallbackService",
        side_effect=AssertionError("callback service should be lazy"),
    ):
        module = _load_callback_module_from_source()

    assert module.receive_callback is not None


def test_callback_route_uses_service_dependency_override() -> None:
    from app.main import app

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "session_id": "sess-123",
        "status": "received",
        "callback_status": "completed",
        "progress": 100,
    }
    mock_service = MagicMock()
    mock_service.process_callback = AsyncMock(return_value=mock_result)

    with _callback_service_override(app, mock_service):
        with (
            patch(
                "app.api.v1.callback.CallbackService",
                side_effect=AssertionError("route should use service override"),
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/callback",
                json={
                    "session_id": "sess-123",
                    "run_id": "run-456",
                    "status": "completed",
                    "progress": 100,
                },
                headers={"Authorization": "Bearer callback-token"},
            )

    assert response.status_code == 200
    assert response.json()["data"]["session_id"] == "sess-123"
    mock_service.process_callback.assert_awaited_once()


def test_callback_service_provider_has_no_mutable_global() -> None:
    from app.api.v1 import callback

    assert not hasattr(callback, "callback_service")


def test_computer_module_import_does_not_initialize_service() -> None:
    with patch(
        "app.services.computer_service.ComputerService",
        side_effect=AssertionError("computer service should be lazy"),
    ):
        module = _load_computer_module_from_source()

    assert module.upload_browser_screenshot is not None


def test_computer_route_uses_service_dependency_override() -> None:
    from app.main import app

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "session_id": "sess-123",
        "tool_use_id": "tool-456",
        "key": "replays/user/sess-123/browser/tool-456.png",
        "content_type": "image/png",
        "size_bytes": 100,
    }
    mock_service = MagicMock()
    mock_service.upload_browser_screenshot.return_value = mock_result

    with _computer_service_override(app, mock_service):
        with (
            patch(
                "app.api.v1.computer.ComputerService",
                side_effect=AssertionError("route should use service override"),
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/computer/screenshots",
                data={"session_id": "sess-123", "tool_use_id": "tool-456"},
                files={
                    "file": (
                        "screenshot.png",
                        io.BytesIO(b"\x89PNG\r\n\x1a\n"),
                        "image/png",
                    )
                },
                headers={"Authorization": "Bearer callback-token"},
            )

    assert response.status_code == 200
    assert response.json()["data"]["session_id"] == "sess-123"
    mock_service.upload_browser_screenshot.assert_called_once()


def test_computer_service_provider_has_no_mutable_global() -> None:
    from app.api.v1 import computer

    assert not hasattr(computer, "computer_service")


class TestCallbackEndpoint(unittest.TestCase):
    """Test /api/v1/callback endpoint."""

    def test_receive_callback_requires_callback_token(self) -> None:
        """Test callback rejects missing callback token."""
        from app.main import app

        with patch(
            "app.core.deps.get_settings",
            return_value=SimpleNamespace(callback_token="callback-token"),
        ):
            mock_service = MagicMock()
            mock_service.process_callback = AsyncMock()
            with _callback_service_override(app, mock_service):
                client = TestClient(app)
                response = client.post(
                    "/api/v1/callback",
                    json={
                        "session_id": "sess-123",
                        "run_id": "run-456",
                        "status": "completed",
                        "progress": 100,
                    },
                )

        assert response.status_code == 403
        mock_service.process_callback.assert_not_called()

    def test_receive_callback_success(self) -> None:
        """Test successful callback processing."""
        from app.main import app

        with patch(
            "app.core.deps.get_settings",
            return_value=SimpleNamespace(callback_token="callback-token"),
        ):
            mock_service = MagicMock()
            with _callback_service_override(app, mock_service):
                mock_result = MagicMock()
                mock_result.model_dump.return_value = {
                    "session_id": "sess-123",
                    "status": "received",
                    "callback_status": "completed",
                    "progress": 100,
                }
                mock_service.process_callback = AsyncMock(return_value=mock_result)

                client = TestClient(app)
                response = client.post(
                    "/api/v1/callback",
                    json={
                        "session_id": "sess-123",
                        "run_id": "run-456",
                        "status": "completed",
                        "progress": 100,
                    },
                    headers={"Authorization": "Bearer callback-token"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["session_id"] == "sess-123"


class TestComputerEndpoint(unittest.TestCase):
    """Test /api/v1/computer/screenshots endpoint."""

    def test_upload_browser_screenshot_requires_callback_token(self) -> None:
        """Test screenshot upload rejects missing callback token."""
        from app.main import app

        with patch(
            "app.core.deps.get_settings",
            return_value=SimpleNamespace(callback_token="callback-token"),
        ):
            mock_service = MagicMock()
            with _computer_service_override(app, mock_service):
                client = TestClient(app)
                fake_image = b"\x89PNG\r\n\x1a\n"

                response = client.post(
                    "/api/v1/computer/screenshots",
                    data={"session_id": "sess-123", "tool_use_id": "tool-456"},
                    files={
                        "file": ("screenshot.png", io.BytesIO(fake_image), "image/png")
                    },
                )

        assert response.status_code == 403
        mock_service.upload_browser_screenshot.assert_not_called()

    def test_upload_browser_screenshot_success(self) -> None:
        """Test successful screenshot upload."""
        from app.main import app

        mock_service = MagicMock()
        with _computer_service_override(app, mock_service):
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "session_id": "sess-123",
                "tool_use_id": "tool-456",
                "key": "replays/user/sess-123/browser/tool-456.png",
                "content_type": "image/png",
                "size_bytes": 100,
            }
            mock_service.upload_browser_screenshot.return_value = mock_result

            with patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ):
                client = TestClient(app)
                fake_image = b"\x89PNG\r\n\x1a\n"  # PNG header

                response = client.post(
                    "/api/v1/computer/screenshots",
                    data={"session_id": "sess-123", "tool_use_id": "tool-456"},
                    files={
                        "file": ("screenshot.png", io.BytesIO(fake_image), "image/png")
                    },
                    headers={"Authorization": "Bearer callback-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["session_id"] == "sess-123"

    def test_upload_browser_screenshot_default_content_type(self) -> None:
        """Test screenshot upload with default content type."""
        from app.main import app

        mock_service = MagicMock()
        with _computer_service_override(app, mock_service):
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "session_id": "sess-123",
                "tool_use_id": "tool-456",
                "key": "replays/user/sess-123/browser/tool-456.png",
                "content_type": "image/png",
                "size_bytes": 100,
            }
            mock_service.upload_browser_screenshot.return_value = mock_result

            with patch(
                "app.core.deps.get_settings",
                return_value=SimpleNamespace(callback_token="callback-token"),
            ):
                client = TestClient(app)
                fake_image = b"fake_image_data"

                # Upload without content type
                response = client.post(
                    "/api/v1/computer/screenshots",
                    data={"session_id": "sess-123", "tool_use_id": "tool-456"},
                    files={"file": ("screenshot.png", io.BytesIO(fake_image))},
                    headers={"Authorization": "Bearer callback-token"},
                )

            assert response.status_code == 200
            # Verify service was called
            mock_service.upload_browser_screenshot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
