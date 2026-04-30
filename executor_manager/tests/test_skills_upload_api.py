"""Tests for app/api/v1/skills_upload.py."""

from contextlib import contextmanager
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient


def _load_skills_upload_module_from_source():
    module_name = "_skills_upload_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "skills_upload.py"
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
def _dependency_overrides(app, *, backend, exporter):
    from app.api.v1 import skills_upload

    app.dependency_overrides[skills_upload.get_backend_client] = lambda: backend
    app.dependency_overrides[skills_upload.get_workspace_export_service] = lambda: (
        exporter
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(skills_upload.get_backend_client, None)
        app.dependency_overrides.pop(skills_upload.get_workspace_export_service, None)


def test_skills_upload_module_import_does_not_initialize_concrete_adapters() -> None:
    with (
        patch(
            "app.services.backend_client.BackendClient",
            side_effect=AssertionError("backend client should be lazy"),
        ),
        patch(
            "app.services.workspace_export_service.WorkspaceExportService",
            side_effect=AssertionError("workspace export should be lazy"),
        ),
    ):
        module = _load_skills_upload_module_from_source()

    assert module.submit_skill is not None


def test_skills_upload_route_uses_dependency_overrides() -> None:
    from app.main import app

    mock_export_result = MagicMock()
    mock_export_result.workspace_export_status = "ready"
    mock_export_result.workspace_files_prefix = "files/prefix/"
    mock_export_result.error = None

    mock_export_service = MagicMock()
    mock_export_service.stage_skill_submission_folder = MagicMock(
        return_value="/staged/skill-folder"
    )
    mock_export_service.export_workspace_folder = MagicMock(
        return_value=mock_export_result
    )

    mock_client = MagicMock()
    mock_client.submit_skill_from_workspace = AsyncMock(
        return_value={
            "data": {"job_id": "skill-job-123"},
            "message": "Skill submission queued",
        }
    )

    mock_settings = MagicMock()
    mock_settings.callback_token = "callback-token"

    with _dependency_overrides(
        app,
        backend=mock_client,
        exporter=mock_export_service,
    ):
        with (
            patch(
                "app.api.v1.skills_upload.BackendClient",
                side_effect=AssertionError("route should use backend override"),
            ),
            patch(
                "app.api.v1.skills_upload.WorkspaceExportService",
                side_effect=AssertionError("route should use exporter override"),
            ),
            patch("app.core.deps.get_settings", return_value=mock_settings),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                    "skill_name": "my-skill",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

    assert response.status_code == 200
    assert response.json()["data"]["job_id"] == "skill-job-123"
    mock_client.submit_skill_from_workspace.assert_awaited_once_with(
        "session-123",
        folder_path="/staged/skill-folder",
        skill_name="my-skill",
        workspace_files_prefix="files/prefix/",
    )


def test_skills_upload_providers_have_no_mutable_globals() -> None:
    from app.api.v1 import skills_upload

    assert not hasattr(skills_upload, "backend_client")
    assert not hasattr(skills_upload, "workspace_export_service")


class TestSkillsUploadEndpoints(unittest.TestCase):
    """Test /api/v1/skills endpoints."""

    def test_submit_skill_success(self) -> None:
        """Test successful skill submission."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "ready"
        mock_export_result.workspace_files_prefix = "files/prefix/"
        mock_export_result.error = None

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        mock_client = MagicMock()
        mock_client.submit_skill_from_workspace = AsyncMock(
            return_value={
                "data": {"job_id": "skill-job-123"},
                "message": "Skill submission queued",
            }
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                    "skill_name": "my-skill",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["job_id"] == "skill-job-123"

    def test_submit_skill_delegates_backend_internal_auth_to_client(self) -> None:
        """Test skill submission does not build internal auth headers in the route."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "ready"
        mock_export_result.workspace_files_prefix = "files/prefix/"
        mock_export_result.error = None

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        mock_client = MagicMock()
        mock_client._request = AsyncMock(
            side_effect=AssertionError("route should use backend client port")
        )
        mock_client.submit_skill_from_workspace = AsyncMock(
            return_value={
                "data": {"job_id": "skill-job-123"},
                "message": "Skill submission queued",
            }
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.api.v1.skills_upload.get_settings",
                side_effect=AssertionError("route should not read settings directly"),
                create=True,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                    "skill_name": "my-skill",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["job_id"] == "skill-job-123"
        mock_client.submit_skill_from_workspace.assert_awaited_once_with(
            "session-123",
            folder_path="/staged/skill-folder",
            skill_name="my-skill",
            workspace_files_prefix="files/prefix/",
        )

    def test_submit_skill_export_not_ready(self) -> None:
        """Test skill submission when export is not ready."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "error"
        mock_export_result.workspace_files_prefix = None
        mock_export_result.error = "Export failed"

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"
        mock_client = MagicMock()

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 400
            data = response.json()
            assert "Export failed" in data["message"]

    def test_submit_skill_export_missing_files(self) -> None:
        """Test skill submission when export has no files."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "ready"
        mock_export_result.workspace_files_prefix = "   "  # Empty/whitespace
        mock_export_result.error = None

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"
        mock_client = MagicMock()

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 400
            data = response.json()
            assert "missing files" in data["message"]

    def test_submit_skill_backend_http_error(self) -> None:
        """Test skill submission with backend HTTP error."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "ready"
        mock_export_result.workspace_files_prefix = "files/prefix/"
        mock_export_result.error = None

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        # Create mock HTTP response
        mock_http_response = MagicMock()
        mock_http_response.status_code = 500
        mock_http_response.text = "Internal Server Error"
        mock_http_response.json.return_value = {"message": "Backend service error"}

        mock_client = MagicMock()
        mock_client.submit_skill_from_workspace = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=mock_http_response,
            )
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 500
            data = response.json()
            assert "Backend service error" in data["message"]

    def test_submit_skill_backend_http_error_no_json(self) -> None:
        """Test skill submission with backend HTTP error (no JSON response)."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "ready"
        mock_export_result.workspace_files_prefix = "files/prefix/"
        mock_export_result.error = None

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        # Create mock HTTP response that fails JSON parsing
        mock_http_response = MagicMock()
        mock_http_response.status_code = 503
        mock_http_response.text = "Service Unavailable"
        mock_http_response.json.side_effect = Exception("Not JSON")

        mock_client = MagicMock()
        mock_client.submit_skill_from_workspace = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Service unavailable",
                request=MagicMock(),
                response=mock_http_response,
            )
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 503
            data = response.json()
            assert "Service Unavailable" in data["message"]

    def test_submit_skill_backend_http_error_with_detail(self) -> None:
        """Test skill submission with backend HTTP error using detail field."""
        from app.main import app

        mock_export_result = MagicMock()
        mock_export_result.workspace_export_status = "ready"
        mock_export_result.workspace_files_prefix = "files/prefix/"
        mock_export_result.error = None

        mock_export_service = MagicMock()
        mock_export_service.stage_skill_submission_folder = MagicMock(
            return_value="/staged/skill-folder"
        )
        mock_export_service.export_workspace_folder = MagicMock(
            return_value=mock_export_result
        )

        # Create mock HTTP response with detail field
        mock_http_response = MagicMock()
        mock_http_response.status_code = 400
        mock_http_response.text = "Bad Request"
        mock_http_response.json.return_value = {"detail": "Invalid skill configuration"}

        mock_client = MagicMock()
        mock_client.submit_skill_from_workspace = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Bad request",
                request=MagicMock(),
                response=mock_http_response,
            )
        )

        mock_settings = MagicMock()
        mock_settings.callback_token = "callback-token"

        with (
            _dependency_overrides(
                app,
                backend=mock_client,
                exporter=mock_export_service,
            ),
            patch(
                "app.core.deps.get_settings",
                return_value=mock_settings,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/skills/submit",
                json={
                    "session_id": "session-123",
                    "folder_path": "/workspace/skill-folder",
                },
                headers={"Authorization": "Bearer callback-token"},
            )

            assert response.status_code == 400
            data = response.json()
            assert "Invalid skill configuration" in data["message"]


if __name__ == "__main__":
    unittest.main()
