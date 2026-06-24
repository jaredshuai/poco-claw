"""Route-level integration tests for the Office viewer API endpoints."""

import asyncio
import importlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.schemas.office import OfficeViewerConfigRequest


OFFICE_ENV = {
    "OFFICE_JWT_SECRET": "testtesttesttesttesttesttesttest",
    "OFFICE_DOCUMENT_SERVER_URL": "http://localhost:8100",
    "OFFICE_CALLBACK_JWT_REQUIRED": "true",
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
    return asyncio.run(coro)


def _actor(user_id: str = "user-1") -> Actor:
    return Actor(user_id=user_id)


def _signed_callback_body(payload: dict) -> dict:
    return {
        "token": jwt.encode(
            payload,
            OFFICE_ENV["OFFICE_JWT_SECRET"],
            algorithm="HS256",
        )
    }


def test_office_module_import_does_not_initialize_storage_service():
    import app.api.v1.office as office_module

    with patch(
        "app.services.storage_service.S3StorageService",
        side_effect=AssertionError("storage should be lazy"),
    ):
        reloaded = importlib.reload(office_module)

    assert reloaded.get_viewer_config is not None
    importlib.reload(office_module)


class TestViewerConfig:
    """Tests for POST /viewer-config route handler."""

    def test_success(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
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
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": '"abc123"',
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )

            result = _run(
                get_viewer_config(request=request, actor=_actor(), db=mock_db)
            )

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
                _run(get_viewer_config(request=request, actor=_actor(), db=mock_db))

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
                _run(get_viewer_config(request=request, actor=_actor(), db=mock_db))

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
                _run(get_viewer_config(request=request, actor=_actor(), db=mock_db))

        assert exc.value.error_code == ErrorCode.BAD_REQUEST

    def test_oversized_manifest(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "big.docx",
                    key="ws/abc/big.docx",
                    size=2 * 1024 * 1024,
                )
            ]
        }
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
            mock_storage.get_object_metadata.return_value = {
                "content_length": 2 * 1024 * 1024,
                "etag": None,
                "last_modified": None,
            }

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, actor=_actor(), db=mock_db))

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
            mock_storage.get_object_metadata.return_value = {
                "content_length": 5 * 1024 * 1024,
                "etag": None,
                "last_modified": None,
            }

            with pytest.raises(AppException) as exc:
                _run(get_viewer_config(request=request, actor=_actor(), db=mock_db))

        assert exc.value.error_code == ErrorCode.BAD_REQUEST
        mock_storage.get_object_metadata.assert_called_once_with("ws/abc/big.xlsx")

    def test_file_within_size_limit_passes(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "small.docx",
                    key="ws/abc/small.docx",
                    size=512 * 1024,
                )
            ]
        }
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
            mock_storage.get_object_metadata.return_value = {
                "content_length": 512 * 1024,
                "etag": None,
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/small.docx?sig=abc"
            )

            result = _run(
                get_viewer_config(request=request, actor=_actor(), db=mock_db)
            )

        assert result.document.fileType == "docx"
        mock_storage.get_object_metadata.assert_called_once_with("ws/abc/small.docx")

    def test_language_passed_through(self):
        from app.api.v1.office import get_viewer_config

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                )
            ]
        }
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
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": None,
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )

            result = _run(
                get_viewer_config(request=request, actor=_actor(), db=mock_db)
            )

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
            result = _run(office_health(_actor=_actor()))

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
            result = _run(office_health(_actor=_actor()))

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
            result = _run(office_health(_actor=_actor()))

        assert result.status_code == 503

    def test_not_configured(self):
        from app.api.v1.office import office_health
        from app.core.settings import get_settings

        with patch.dict(os.environ, {"OFFICE_DOCUMENT_SERVER_URL": ""}, clear=False):
            get_settings.cache_clear()
            result = _run(office_health(_actor=_actor()))
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
            result = _run(office_health(_actor=_actor()))

        assert result.status_code == 503


class TestOfficeDownloadLatest:
    """Tests for GET /office/download-latest route handler."""

    def test_download_latest_presigns_current_workspace_object(self):
        from app.api.v1.office import download_latest

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=2048,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 2048,
                "etag": "etag-v2",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?latest=1"
            )

            result = _run(
                download_latest(
                    session_id="00000000-0000-0000-0000-000000000012",
                    file_path="report.docx",
                    actor=_actor(),
                    db=mock_db,
                )
            )

        assert result.url == "https://s3.example.com/report.docx?latest=1"
        assert result.file_path == "report.docx"
        assert result.expires_in == 3600
        mock_storage.presign_get.assert_called_once_with(
            "ws/abc/report.docx",
            response_content_disposition='attachment; filename="report.docx"',
            response_content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            expires_in=3600,
        )


class TestOfficeEditingFlow:
    """Tests for the minimal OnlyOffice editing save loop.

    Each test patches app.api.v1.office.editing_store to bypass the DB.
    """

    @pytest.fixture(autouse=True)
    def _mock_editing_store(self, request):
        from tests.office_test_helpers import make_edit_session, make_save_request

        with patch("app.api.v1.office.editing_store") as mock_store:
            # Use a fixed session_id that tests can match against
            base_es = make_edit_session(
                session_id="00000000-0000-0000-0000-000000000002"
            )
            base_sr = make_save_request(
                edit_session_id=base_es.id, status="pending"
            )

            self._last_es = base_es
            self._save_status = "pending"
            self._base_sr = make_save_request(
                edit_session_id=base_es.id, status="pending"
            )

            def _create_es(*a, **kw):
                es = make_edit_session(
                    session_id=str(kw.get("session_id", base_es.session_id)),
                    document_key=str(kw.get("document_key", base_es.document_key)),
                    callback_token=secrets.token_urlsafe(16),
                )
                self._last_es = es
                self._base_sr.edit_session_id = es.id
                return es

            def _make_matching_sr(*a, **kw):
                sr = make_save_request(
                    edit_session_id=self._last_es.id,
                    status=self._save_status,
                )
                sr.id = self._base_sr.id
                return sr

            mock_store.create_edit_session.side_effect = _create_es
            mock_store.get_edit_session.side_effect = (
                lambda *a, **kw: self._last_es
            )
            mock_store.resolve_by_token.side_effect = (
                lambda *a, **kw: self._last_es
            )
            mock_store.get_save_request.side_effect = _make_matching_sr
            mock_store.create_save_request.side_effect = _make_matching_sr
            mock_store.try_begin_commit.side_effect = _make_matching_sr

            def _mark_saved(*a, **kw):
                self._save_status = "saved"

            def _mark_failed(*a, **kw):
                self._save_status = "failed"

            mock_store.mark_saving = MagicMock()
            mock_store.mark_staged = MagicMock()
            mock_store.complete_save_request = MagicMock(side_effect=_mark_saved)
            mock_store.mark_failed = MagicMock(side_effect=_mark_failed)
            mock_store.discard_edit_session.return_value = True
            mock_store.get_active_save_request.return_value = None
            mock_store.create_save_request.return_value = base_sr
            # get_edit_session — patched per-test on demand
            self._mock_store = mock_store
            self._base_es = base_es
            self._base_sr = base_sr
            yield

    def _set_edit_session(self, session_id: str):
        """Configure the mock store to return a session matching the given id."""
        from tests.office_test_helpers import make_edit_session
        self._mock_store.get_edit_session.side_effect = (
            lambda *a, **kw: make_edit_session(session_id=session_id)
        )

    def test_edit_viewer_config_returns_edit_session_and_callback_url(self):
        from app.api.v1.office import get_viewer_config
        import jwt

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )

            result = _run(
                get_viewer_config(request=request, actor=_actor(), db=mock_db)
            )

        assert result.editorConfig.mode == "edit"
        assert result.edit_session_id
        assert result.editorConfig.callbackUrl
        callback_url = result.editorConfig.callbackUrl
        assert callback_url.startswith("http://localhost:8000/api/v1/office/callback")
        assert parse_qs(urlparse(callback_url).query)["token"][0]

        payload = jwt.decode(
            result.token,
            OFFICE_ENV["OFFICE_JWT_SECRET"],
            algorithms=["HS256"],
        )
        assert payload["editorConfig"]["mode"] == "edit"
        assert payload["editorConfig"]["callbackUrl"] == callback_url

    def _mock_edit_session_for(self, session_id: str):
        """Configure the mock store's get_edit_session to return a session
        that will pass the ForceSave/use-case validation checks."""
        from tests.office_test_helpers import make_edit_session
        es = make_edit_session(session_id=session_id)
        self._mock_store.get_edit_session.return_value = es
        return es

    def test_forcesave_sends_save_request_id_as_userdata(self):
        from app.api.v1.office import force_save, get_viewer_config
        from app.schemas.office import OfficeForceSaveRequest

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000002",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        self._set_edit_session(str(config_request.session_id))

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            result = _run(force_save(request=save_request, actor=_actor(), db=mock_db))

        assert result.status == "saving"
        assert result.save_request_id == str(self._base_sr.id)

    def test_duplicate_forcesave_returns_conflict_with_active_request_id(self):
        from fastapi import HTTPException

        from app.api.v1.office import force_save, get_viewer_config
        from app.schemas.office import OfficeForceSaveRequest

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000011",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            self._set_edit_session(str(config_request.session_id))
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            first = _run(force_save(request=save_request, actor=_actor(), db=mock_db))

            self._mock_store.get_active_save_request.return_value = self._base_sr
            with pytest.raises(HTTPException) as exc:
                _run(force_save(request=save_request, actor=_actor(), db=mock_db))

        assert exc.value.status_code == 409
        assert exc.value.detail == {
            "message": "save_in_progress",
            "active_save_request_id": first.save_request_id,
        }

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_status_6_writes_back_and_marks_save_saved(self):
        from app.api.v1.office import (
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000003",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(request=save_request, actor=_actor(), db=mock_db)
            )

        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata=save_result.save_request_id,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        mock_response = MagicMock()
        mock_response.content = b"new docx bytes"
        mock_response.headers = {
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.office_callback_save_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": len(b"new docx bytes"),
                "etag": "etag-v2",
                "last_modified": "2026-04-26T00:00:00Z",
            }

            _run(office_callback(token=callback_token, request=callback_body))

            writeback_put = mock_storage.put_object.call_args_list[0].kwargs
            assert writeback_put["key"] != "ws/abc/report.docx"
            assert writeback_put["key"].startswith("ws/abc/.office-saves/")
            assert writeback_put["key"].endswith("/report.docx")
            assert writeback_put["body"] == b"new docx bytes"
            assert (
                writeback_put["content_type"]
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            mock_storage.get_object_metadata.assert_called_with(writeback_put["key"])
            manifest_put = mock_storage.put_object.call_args_list[-1].kwargs

        assert manifest_put["key"] == "manifest.json"
        assert writeback_put["key"].encode() in manifest_put["body"]
        assert b"etag-v2" in manifest_put["body"]

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )
        assert status.status == "saved"

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_status_6_ignores_duplicate_while_commit_in_progress(self):
        from app.api.v1.office import (
            editing_store,
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000105",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(
                    request=OfficeForceSaveRequest(
                        session_id=config_request.session_id,
                        file_path="report.docx",
                        edit_session_id=config.edit_session_id,
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )

        assert (
            editing_store.try_begin_commit(
                save_result.save_request_id,
                edit_session_id=config.edit_session_id,
            )
            is not None
        )

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )
        assert status.status == "saving"

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata=save_result.save_request_id,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.office_callback_save_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            _run(office_callback(token=callback_token, request=callback_body))

        mock_client.get.assert_not_called()
        mock_storage.put_object.assert_not_called()

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_manifest_failure_does_not_overwrite_original_object(self):
        from app.api.v1.office import (
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000103",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(request=save_request, actor=_actor(), db=mock_db)
            )

        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata=save_result.save_request_id,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        mock_response = MagicMock()
        mock_response.content = b"new docx bytes"
        mock_response.headers = {
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.office_callback_save_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.api.v1.office.storage_service") as mock_storage,
            pytest.raises(AppException),
        ):
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": len(b"new docx bytes"),
                "etag": "etag-v2",
                "last_modified": "2026-04-26T00:00:00Z",
            }

            def put_object_side_effect(*, key, body, content_type=None):
                if key == "manifest.json":
                    raise AppException(
                        error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                        message="manifest update failed",
                    )

            mock_storage.put_object.side_effect = put_object_side_effect

            _run(office_callback(token=callback_token, request=callback_body))

        put_keys = [
            call.kwargs["key"] for call in mock_storage.put_object.call_args_list
        ]
        assert "ws/abc/report.docx" not in put_keys
        staged_key = next(
            key for key in put_keys if key.startswith("ws/abc/.office-saves/")
        )
        mock_storage.delete_object.assert_called_once_with(staged_key)

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )
        assert status.status == "failed"
        assert status.error_code == "writeback_failed"

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_state_commit_failure_does_not_mark_committed_writeback_failed(
        self,
    ):
        from app.api.v1.office import (
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000104",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(request=save_request, actor=_actor(), db=mock_db)
            )

        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata=save_result.save_request_id,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        mock_response = MagicMock()
        mock_response.content = b"new docx bytes"
        mock_response.headers = {
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.office_callback_save_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.api.v1.office.storage_service") as mock_storage,
            patch(
                "app.api.v1.office.editing_store.complete_save_request",
                side_effect=RuntimeError("state commit failed"),
                create=True,
            ),
            pytest.raises(RuntimeError, match="state commit failed"),
        ):
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": len(b"new docx bytes"),
                "etag": "etag-v2",
                "last_modified": "2026-04-26T00:00:00Z",
            }

            _run(office_callback(token=callback_token, request=callback_body))

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )
        # Recovery marker + cleanup_expired should have auto-recovered
        # the stuck COMMITTING save_request to SAVED.
        assert status.status == "saved"
        assert status.error_code is None

    def test_callback_rejects_missing_onlyoffice_jwt(self):
        from app.api.v1.office import (
            force_save,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000005",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(request=save_request, actor=_actor(), db=mock_db)
            )

        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata=save_result.save_request_id,
        )

        with pytest.raises(AppException) as exc:
            _run(
                office_callback(
                    token=callback_token,
                    request=callback.model_dump(exclude_none=True),
                )
            )

        assert exc.value.error_code == ErrorCode.FORBIDDEN

    def test_callback_rejects_download_url_outside_document_server(self):
        from app.api.v1.office import (
            force_save,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [
                _file_entry(
                    "report.docx",
                    key="ws/abc/report.docx",
                    size=1024,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000004",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(request=save_request, actor=_actor(), db=mock_db)
            )

        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://169.254.169.254/latest/meta-data",
            userdata=save_result.save_request_id,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        mock_response = MagicMock()
        mock_response.content = b"metadata"
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.office_callback_save_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.api.v1.office.storage_service") as mock_storage,
            pytest.raises(AppException) as exc,
        ):
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": len(b"metadata"),
                "etag": "etag-v2",
                "last_modified": "2026-04-26T00:00:00Z",
            }
            _run(office_callback(token=callback_token, request=callback_body))

        assert exc.value.error_code == ErrorCode.FORBIDDEN
        mock_client.get.assert_not_called()
        mock_storage.put_object.assert_not_called()

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_discard_edit_session_revokes_save_and_callback(self):
        from app.api.v1.office import (
            discard_edit_session,
            force_save,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeDiscardEditSessionRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000006",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        discard_request = OfficeDiscardEditSessionRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with patch("app.api.v1.office.session_service") as mock_ss:
            mock_ss.get_session.return_value = session
            discard_result = _run(
                discard_edit_session(
                    request=discard_request,
                    actor=_actor(),
                    db=mock_db,
                )
            )

        assert discard_result.status == "discarded"

        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with patch("app.api.v1.office.session_service") as mock_ss:
            mock_ss.get_session.return_value = session
            with pytest.raises(AppException) as exc:
                _run(force_save(request=save_request, actor=_actor(), db=mock_db))

        assert exc.value.error_code == ErrorCode.BAD_REQUEST

        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata="save-request-after-discard",
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        with pytest.raises(AppException) as exc:
            _run(office_callback(token=callback_token, request=callback_body))

        assert exc.value.error_code == ErrorCode.FORBIDDEN

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_save_status_returns_failed_when_edit_session_expires(self):
        from app.api.v1.office import (
            editing_store,
            force_save,
            get_save_status,
            get_viewer_config,
        )
        from app.schemas.office import OfficeForceSaveRequest

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000007",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        save_request = OfficeForceSaveRequest(
            session_id=config_request.session_id,
            file_path="report.docx",
            edit_session_id=config.edit_session_id,
        )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(request=save_request, actor=_actor(), db=mock_db)
            )

        edit_session = editing_store.get_edit_session(config.edit_session_id)
        assert edit_session is not None
        edit_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )

        assert status.status == "failed"
        assert status.error_code == "office_edit_session_expired"

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_status_7_ignores_userdata_from_other_edit_session(self):
        from app.api.v1.office import (
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [
                _file_entry("a.docx", key="ws/abc/a.docx", size=1024),
                _file_entry("b.docx", key="ws/abc/b.docx", size=1024),
            ]
        }
        session_id = "00000000-0000-0000-0000-000000000008"
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/doc.docx?sig=abc"
            )
            config_a = _run(
                get_viewer_config(
                    request=OfficeViewerConfigRequest(
                        session_id=session_id,
                        file_path="a.docx",
                        mode="edit",
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )
            config_b = _run(
                get_viewer_config(
                    request=OfficeViewerConfigRequest(
                        session_id=session_id,
                        file_path="b.docx",
                        mode="edit",
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_a = _run(
                force_save(
                    request=OfficeForceSaveRequest(
                        session_id=session_id,
                        file_path="a.docx",
                        edit_session_id=config_a.edit_session_id,
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )

        callback_token_b = parse_qs(urlparse(config_b.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        callback = OfficeCallbackRequest(
            status=7,
            key=config_b.document.key,
            userdata=save_a.save_request_id,
            error=1,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        _run(office_callback(token=callback_token_b, request=callback_body))

        status = _run(
            get_save_status(
                session_id=session_id,
                save_request_id=save_a.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )

        assert status.status == "saving"

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_status_7_marks_same_edit_session_save_failed(self):
        from app.api.v1.office import (
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000009",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(
                    request=OfficeForceSaveRequest(
                        session_id=config_request.session_id,
                        file_path="report.docx",
                        edit_session_id=config.edit_session_id,
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        callback = OfficeCallbackRequest(
            status=7,
            key=config.document.key,
            userdata=save_result.save_request_id,
            error=123,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        _run(office_callback(token=callback_token, request=callback_body))

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )

        assert status.status == "failed"
        assert status.error_code == "office_forcesave_failed"
        assert status.error_message == "123"

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_status_7_does_not_regress_saved_request(self):
        from app.api.v1.office import (
            editing_store,
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000011",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(
                    request=OfficeForceSaveRequest(
                        session_id=config_request.session_id,
                        file_path="report.docx",
                        edit_session_id=config.edit_session_id,
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )

        editing_store.mark_saved(save_result.save_request_id)

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        callback = OfficeCallbackRequest(
            status=7,
            key=config.document.key,
            userdata=save_result.save_request_id,
            error=123,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        _run(office_callback(token=callback_token, request=callback_body))

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )

        assert status.status == "saved"
        assert status.error_code is None

    @pytest.mark.xfail(reason="needs rewrite for DB-backed store (191c2db9)", strict=False)
    def test_callback_status_6_does_not_write_back_failed_save_request(self):
        from app.api.v1.office import (
            editing_store,
            force_save,
            get_save_status,
            get_viewer_config,
            office_callback,
        )
        from app.schemas.office import (
            OfficeCallbackRequest,
            OfficeForceSaveRequest,
        )

        session = _make_session()
        manifest = {
            "files": [_file_entry("report.docx", key="ws/abc/report.docx", size=1024)]
        }
        config_request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000010",
            file_path="report.docx",
            mode="edit",
        )
        mock_db = MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            mock_ss.get_session.return_value = session
            mock_storage.get_manifest.return_value = manifest
            mock_storage.get_object_metadata.return_value = {
                "content_length": 1024,
                "etag": "etag-v1",
                "last_modified": None,
            }
            mock_storage.presign_get.return_value = (
                "https://s3.example.com/report.docx?sig=abc"
            )
            config = _run(
                get_viewer_config(request=config_request, actor=_actor(), db=mock_db)
            )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.command_client") as mock_command,
        ):
            mock_ss.get_session.return_value = session
            mock_command.forcesave = AsyncMock(return_value=None)
            save_result = _run(
                force_save(
                    request=OfficeForceSaveRequest(
                        session_id=config_request.session_id,
                        file_path="report.docx",
                        edit_session_id=config.edit_session_id,
                    ),
                    actor=_actor(),
                    db=mock_db,
                )
            )

        editing_store.mark_failed(
            save_result.save_request_id,
            error_code="manual_failure",
        )

        callback_token = parse_qs(urlparse(config.editorConfig.callbackUrl).query)[
            "token"
        ][0]
        callback = OfficeCallbackRequest(
            status=6,
            key=config.document.key,
            url="http://localhost:8100/cache/report.docx",
            userdata=save_result.save_request_id,
        )
        callback_body = _signed_callback_body(callback.model_dump(exclude_none=True))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.office_callback_save_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.api.v1.office.storage_service") as mock_storage,
        ):
            _run(office_callback(token=callback_token, request=callback_body))

        mock_client.get.assert_not_called()
        mock_storage.put_object.assert_not_called()

        status = _run(
            get_save_status(
                session_id=config_request.session_id,
                save_request_id=save_result.save_request_id,
                actor=_actor(),
                db=mock_db,
            )
        )

        assert status.status == "failed"
        assert status.error_code == "manual_failure"


class TestActorBoundaryMigration:
    """Focused tests proving the Actor boundary migration."""

    def test_office_module_does_not_import_get_current_user_id(self):
        """office.py should not expose get_current_user_id after migration."""
        import app.api.v1.office as office_module

        assert not hasattr(office_module, "get_current_user_id")
        assert hasattr(office_module, "get_current_actor")

    def test_get_viewer_config_passes_actor_user_id_to_command(self):
        """get_viewer_config should pass actor.user_id to OfficeViewerConfigCommand."""
        from app.api.v1.office import get_viewer_config
        from app.services.office_viewer_config_use_case import (
            OfficeViewerConfigCommand,
            OfficeViewerConfigUseCase,
        )

        session = _make_session()
        request = OfficeViewerConfigRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
        )
        mock_db = MagicMock()
        actor = _actor(user_id="actor-user-viewer")

        captured_command = None

        def capture_command(db, cmd: OfficeViewerConfigCommand):
            nonlocal captured_command
            captured_command = cmd
            return MagicMock()

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.OfficeViewerConfigUseCase") as mock_uc_class,
        ):
            mock_ss.get_session.return_value = session
            mock_uc_instance = MagicMock(spec=OfficeViewerConfigUseCase)
            mock_uc_instance.execute.side_effect = capture_command
            mock_uc_class.return_value = mock_uc_instance

            _run(get_viewer_config(request=request, actor=actor, db=mock_db))

        assert captured_command is not None
        assert captured_command.user_id == "actor-user-viewer"

    def test_download_latest_passes_actor_user_id_to_command(self):
        """download_latest should pass actor.user_id to OfficeDownloadLatestCommand."""
        from app.api.v1.office import download_latest
        from app.services.office_download_latest_service import (
            OfficeDownloadLatestCommand,
            OfficeDownloadLatestUseCase,
        )

        session = _make_session()
        mock_db = MagicMock()
        actor = _actor(user_id="actor-user-download")

        captured_command = None

        def capture_command(cmd: OfficeDownloadLatestCommand):
            nonlocal captured_command
            captured_command = cmd
            return MagicMock(
                url="https://s3.example.com/file",
                file_path="test.docx",
                expires_in=3600,
            )

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.OfficeDownloadLatestUseCase") as mock_uc_class,
        ):
            mock_ss.get_session.return_value = session
            mock_uc_instance = MagicMock(spec=OfficeDownloadLatestUseCase)
            mock_uc_instance.execute.side_effect = capture_command
            mock_uc_class.return_value = mock_uc_instance

            _run(
                download_latest(
                    session_id="00000000-0000-0000-0000-000000000012",
                    file_path="report.docx",
                    actor=actor,
                    db=mock_db,
                )
            )

        assert captured_command is not None
        assert captured_command.user_id == "actor-user-download"

    def test_force_save_passes_actor_user_id_to_command(self):
        """force_save should pass actor.user_id to OfficeForceSaveCommand."""
        from app.api.v1.office import force_save
        from app.schemas.office import OfficeForceSaveRequest
        from app.services.office_force_save_service import (
            OfficeForceSaveCommand,
            OfficeForceSaveUseCase,
        )

        session = _make_session()
        request = OfficeForceSaveRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
            edit_session_id="edit-session-123",
        )
        mock_db = MagicMock()
        actor = _actor(user_id="actor-user-forcesave")

        captured_command = None

        async def capture_command(db, cmd: OfficeForceSaveCommand):
            nonlocal captured_command
            captured_command = cmd
            return MagicMock(save_request_id="save-123", status="pending")

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.OfficeForceSaveUseCase") as mock_uc_class,
        ):
            mock_ss.get_session.return_value = session
            mock_uc_instance = MagicMock(spec=OfficeForceSaveUseCase)
            mock_uc_instance.execute.side_effect = capture_command
            mock_uc_class.return_value = mock_uc_instance

            _run(force_save(request=request, actor=actor, db=mock_db))

        assert captured_command is not None
        assert captured_command.user_id == "actor-user-forcesave"

    def test_get_save_status_passes_actor_user_id_to_query(self):
        """get_save_status should pass actor.user_id to OfficeSaveStatusQuery."""
        from app.api.v1.office import get_save_status
        from app.services.office_save_status_service import (
            OfficeSaveStatusQuery,
            OfficeSaveStatusUseCase,
        )

        mock_db = MagicMock()
        actor = _actor(user_id="actor-user-savestatus")

        captured_query = None

        def capture_query(db, q: OfficeSaveStatusQuery):
            nonlocal captured_query
            captured_query = q
            return MagicMock(
                save_request_id="save-123",
                status="saved",
                error_code=None,
                error_message=None,
                completed_at=None,
            )

        with (
            patch("app.api.v1.office.OfficeSaveStatusUseCase") as mock_uc_class,
        ):
            mock_uc_instance = MagicMock(spec=OfficeSaveStatusUseCase)
            mock_uc_instance.execute.side_effect = capture_query
            mock_uc_class.return_value = mock_uc_instance

            _run(
                get_save_status(
                    session_id="00000000-0000-0000-0000-000000000001",
                    save_request_id="save-123",
                    actor=actor,
                    db=mock_db,
                )
            )

        assert captured_query is not None
        assert captured_query.user_id == "actor-user-savestatus"

    def test_discard_edit_session_passes_actor_user_id_to_command(self):
        """discard_edit_session should pass actor.user_id to OfficeDiscardEditSessionCommand."""
        from app.api.v1.office import discard_edit_session
        from app.schemas.office import OfficeDiscardEditSessionRequest
        from app.services.office_discard_edit_session_service import (
            OfficeDiscardEditSessionCommand,
            OfficeDiscardEditSessionUseCase,
        )

        session = _make_session()
        request = OfficeDiscardEditSessionRequest(
            session_id="00000000-0000-0000-0000-000000000001",
            file_path="report.docx",
            edit_session_id="edit-session-123",
        )
        mock_db = MagicMock()
        actor = _actor(user_id="actor-user-discard")

        captured_command = None

        def capture_command(db, cmd: OfficeDiscardEditSessionCommand):
            nonlocal captured_command
            captured_command = cmd
            return MagicMock(edit_session_id="edit-session-123", status="discarded")

        with (
            patch("app.api.v1.office.session_service") as mock_ss,
            patch("app.api.v1.office.OfficeDiscardEditSessionUseCase") as mock_uc_class,
        ):
            mock_ss.get_session.return_value = session
            mock_uc_instance = MagicMock(spec=OfficeDiscardEditSessionUseCase)
            mock_uc_instance.execute.side_effect = capture_command
            mock_uc_class.return_value = mock_uc_instance

            _run(discard_edit_session(request=request, actor=actor, db=mock_db))

        assert captured_command is not None
        assert captured_command.user_id == "actor-user-discard"

    def test_office_health_uses_actor_auth(self):
        """office_health should require Actor authentication via _actor parameter."""
        from app.api.v1.office import office_health
        from inspect import signature

        sig = signature(office_health)
        params = list(sig.parameters.keys())
        assert "_actor" in params

    def test_office_callback_remains_without_actor_auth(self):
        """office_callback should not require Actor auth and use token/JWT path."""
        from app.api.v1.office import office_callback
        from inspect import signature

        sig = signature(office_callback)
        params = list(sig.parameters.keys())
        assert "actor" not in params
        assert "_actor" not in params
        assert "token" in params
