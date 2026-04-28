import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_editing_service import OfficeEditSession
from app.services.office_viewer_config_use_case import (
    OfficeViewerConfigCommand,
    OfficeViewerConfigUseCase,
)


OFFICE_ENV = {
    "OFFICE_JWT_SECRET": "testtesttesttesttesttesttesttest",
    "OFFICE_DOCUMENT_SERVER_URL": "http://localhost:8100",
}


@pytest.fixture(autouse=True)
def _setup_settings():
    with patch.dict(os.environ, OFFICE_ENV, clear=False):
        from app.core.settings import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


def _file_entry(
    path: str,
    *,
    key: str | None = None,
    mime_type: str | None = None,
    size: int | None = None,
) -> dict:
    entry = {"path": path}
    if key is not None:
        entry["key"] = key
    if mime_type is not None:
        entry["mimeType"] = mime_type
    if size is not None:
        entry["size"] = size
    return entry


def _command(**overrides: str | int | None) -> OfficeViewerConfigCommand:
    values = {
        "session_id": "session-123",
        "session_user_id": "user-123",
        "user_id": "user-123",
        "file_path": "docs/report.docx",
        "file_type": None,
        "language": "en",
        "mode": "view",
        "edit_session_id": None,
        "workspace_manifest_key": "manifest.json",
        "workspace_files_prefix": "ws/abc",
        "file_size_limit_bytes": 1024 * 1024,
        "presign_expires_in": 3600,
        "callback_base_url": "http://callback/api/v1",
    }
    values.update(overrides)
    return OfficeViewerConfigCommand(**values)


def _edit_session() -> OfficeEditSession:
    return OfficeEditSession(
        edit_session_id="edit-123",
        session_id="session-123",
        user_id="user-123",
        file_path="docs/report.docx",
        object_key="ws/abc/docs/report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        manifest_key="manifest.json",
        document_key="doc-key",
        callback_token="callback-token",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def _storage_service() -> MagicMock:
    storage_service = MagicMock()
    storage_service.get_manifest.return_value = {
        "files": [
            _file_entry(
                "docs/report.docx",
                key="ws/abc/docs/report.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                size=2048,
            )
        ]
    }
    storage_service.get_object_metadata.return_value = {
        "content_length": 2048,
        "etag": "etag-v1",
        "last_modified": None,
    }
    storage_service.presign_get.return_value = "https://s3.example.com/report.docx"
    return storage_service


def test_viewer_config_presigns_workspace_file_for_view_mode() -> None:
    storage_service = _storage_service()
    editing_store = MagicMock()

    result = OfficeViewerConfigUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
    ).execute(_command())

    assert result.document.title == "report.docx"
    assert result.document.url == "https://s3.example.com/report.docx"
    assert result.editorConfig.mode == "view"
    assert result.edit_session_id is None
    editing_store.create_edit_session.assert_not_called()
    storage_service.presign_get.assert_called_once_with(
        "ws/abc/docs/report.docx",
        response_content_disposition="inline",
        response_content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        expires_in=3600,
    )


def test_viewer_config_creates_edit_session_and_callback_url() -> None:
    storage_service = _storage_service()
    editing_store = MagicMock()
    editing_store.create_edit_session.return_value = _edit_session()

    result = OfficeViewerConfigUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
    ).execute(_command(mode="edit", edit_session_id="edit-123"))

    assert result.edit_session_id == "edit-123"
    assert result.editorConfig.mode == "edit"
    assert (
        result.editorConfig.callbackUrl
        == "http://callback/api/v1/office/callback?token=callback-token"
    )
    editing_store.create_edit_session.assert_called_once()
    assert editing_store.create_edit_session.call_args.kwargs["document_key"]


def test_viewer_config_rejects_too_large_file() -> None:
    storage_service = _storage_service()
    storage_service.get_manifest.return_value = {
        "files": [
            _file_entry("docs/report.docx", key="ws/abc/docs/report.docx", size=2)
        ]
    }

    with pytest.raises(AppException) as exc_info:
        OfficeViewerConfigUseCase(
            storage_service=storage_service,
            editing_store=MagicMock(),
        ).execute(_command(file_size_limit_bytes=1))

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST
    assert "too large" in exc_info.value.message
    storage_service.presign_get.assert_not_called()


def test_viewer_config_rejects_session_owner_mismatch() -> None:
    storage_service = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeViewerConfigUseCase(
            storage_service=storage_service,
            editing_store=MagicMock(),
        ).execute(_command(session_user_id="other-user"))

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
    storage_service.get_manifest.assert_not_called()
