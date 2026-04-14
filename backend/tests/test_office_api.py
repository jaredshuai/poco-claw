"""Route-level integration tests for the Office viewer API endpoints."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeViewerConfigRequest


OFFICE_ENV = {
    "OFFICE_JWT_SECRET": "test-secret-key",
    "OFFICE_DOCUMENT_SERVER_URL": "http://localhost:8100",
    "OFFICE_FILE_SIZE_LIMIT_MB": "1",
    "OFFICE_PRESIGN_EXPIRES_SECONDS": "3600",
    "S3_BUCKET": "test-bucket",
    "S3_ENDPOINT": "http://localhost:9000",
    "S3_ACCESS_KEY": "minioadmin",
    "S3_SECRET_KEY": "minioadmin",
}


@pytest.fixture(autouse=True)
def _setup_settings():
    with patch.dict(os.environ, OFFICE_ENV, clear=False):
        from app.core.settings import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


def _make_session(user_id="user-1", manifest_key="manifest.json", prefix="ws/abc"):
    s = MagicMock()
    s.user_id = user_id
    s.workspace_manifest_key = manifest_key
    s.workspace_files_prefix = prefix
    return s


def _file_entry(path, *, key=None, size=None, mime_type=None):
    entry = {"path": path}
    if key is not None:
        entry["key"] = key
    if size is not None:
        entry["size"] = size
    if mime_type is not None:
        entry["mimeType"] = mime_type
    return entry


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestViewerConfig:
    """Tests for POST /viewer-config route handler."""

    def test_success(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {"files": [_file_entry(
            "report.docx",
            key="ws/abc/report.docx",
            size=1024,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )]}
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.presign_get.return_value = "https://s3.example.com/report.docx?sig=abc"

            result = _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert result.document.fileType == "docx"
        assert result.document.url == "https://s3.example.com/report.docx?sig=abc"
        assert result.documentType == "word"
        assert result.editorConfig.mode == "view"
        assert result.token

    def test_wrong_user_forbidden(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session(user_id="other-user")
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
        )
        mock_db = MagicMock()

        with patch("app.api.v1.office.session_service") as mock_ss:
            mock_ss.get_session.return_value = session

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert exc.value.error_code == ErrorCode.FORBIDDEN

    def test_missing_session_not_found(self):
        from app.api.v1.office import get_viewer_config

        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000099",
            file_path="report.docx",
        )
        mock_db = MagicMock()

        with patch("app.api.v1.office.session_service") as mock_ss:
            mock_ss.get_session.side_effect = AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Session not found",
            )

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert exc.value.error_code == ErrorCode.NOT_FOUND

    def test_invalid_path_traversal(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="../etc/passwd",
        )
        mock_db = MagicMock()

        with patch("app.api.v1.office.session_service") as mock_ss:
            mock_ss.get_session.return_value = session

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert exc.value.error_code == ErrorCode.BAD_REQUEST

    def test_oversized_manifest(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {"files": [_file_entry(
            "big.docx", key="ws/abc/big.docx", size=2 * 1024 * 1024,
        )]}
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="big.docx",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert exc.value.error_code == ErrorCode.BAD_REQUEST
        assert "too large" in exc.value.message.lower()

    def test_oversized_headobject_fallback(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {"files": [_file_entry("big.xlsx", key="ws/abc/big.xlsx")]}
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="big.xlsx",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_size.return_value = 5 * 1024 * 1024

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert exc.value.error_code == ErrorCode.BAD_REQUEST
        mock_storage.get_object_size.assert_called_once_with("ws/abc/big.xlsx")

    def test_file_within_size_limit_passes(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {"files": [_file_entry(
            "small.docx", key="ws/abc/small.docx", size=512 * 1024,
        )]}
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="small.docx",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.presign_get.return_value = "https://s3.example.com/small.docx?sig=abc"

            result = _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert result.document.fileType == "docx"
        mock_storage.get_object_size.assert_not_called()

    def test_language_passed_through(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {"files": [_file_entry(
            "report.docx", key="ws/abc/report.docx", size=1024,
        )]}
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
            language="zh",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.presign_get.return_value = "https://s3.example.com/report.docx?sig=abc"

            result = _run(get_viewer_config(request=request, user_id="user-1", db=mock_db))

        assert result.editorConfig.lang == "zh"


class TestOfficeHealth:
    """Tests for GET /office/health endpoint."""

    def test_configured_and_healthy(self):
        from app.api.v1.office import office_health

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "true"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.office.httpx.AsyncClient", return_value=mock_client):
            result = _run(office_health(user_id="user-1"))

        assert result.status_code == 200

    def test_configured_and_unhealthy(self):
        from app.api.v1.office import office_health

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "false"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.office.httpx.AsyncClient", return_value=mock_client):
            result = _run(office_health(user_id="user-1"))

        assert result.status_code == 503

    def test_ds_returns_500(self):
        from app.api.v1.office import office_health

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.office.httpx.AsyncClient", return_value=mock_client):
            result = _run(office_health(user_id="user-1"))

        assert result.status_code == 503

    def test_not_configured(self):
        from app.api.v1.office import office_health
        from app.core.settings import get_settings

        with patch.dict(os.environ, {"OFFICE_DOCUMENT_SERVER_URL": ""}, clear=False):
            get_settings.cache_clear()
            result = _run(office_health(user_id="user-1"))
            get_settings.cache_clear()

        assert result.status_code == 503

    def test_connection_error(self):
        from app.api.v1.office import office_health
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.office.httpx.AsyncClient", return_value=mock_client):
            result = _run(office_health(user_id="user-1"))

        assert result.status_code == 503
