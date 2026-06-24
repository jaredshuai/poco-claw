import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_viewer_config_use_case import (
    OfficeViewerConfigCommand,
    OfficeViewerConfigUseCase,
)
from tests.office_test_helpers import make_edit_session


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


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


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
    db = MagicMock(spec=Session)
    storage_service = _storage_service()
    editing_store = MagicMock()

    result = OfficeViewerConfigUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
    ).execute(db, _command())

    assert result.document.title == "report.docx"
    assert result.document.url == "https://s3.example.com/report.docx"
    assert result.editorConfig.mode == "view"
    assert result.edit_session_id is None
    editing_store.create_edit_session.assert_not_called()


def test_viewer_config_creates_edit_session_and_callback_url() -> None:
    db = MagicMock(spec=Session)
    storage_service = _storage_service()
    editing_store = MagicMock()
    es = make_edit_session()
    editing_store.create_edit_session.return_value = es

    result = OfficeViewerConfigUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
    ).execute(db, _command(mode="edit", edit_session_id=str(es.id)))

    assert result.editorConfig.mode == "edit"
    assert (
        result.editorConfig.callbackUrl
        == "http://callback/api/v1/office/callback?token=callback-token"
    )
    editing_store.create_edit_session.assert_called_once()


def test_viewer_config_uses_injected_id_generator_for_edit_session_id() -> None:
    db = MagicMock(spec=Session)
    storage_service = _storage_service()
    editing_store = MagicMock()
    es = make_edit_session()
    editing_store.create_edit_session.return_value = es

    result = OfficeViewerConfigUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
        id_generator=FixedIdGenerator(str(es.id)),
    ).execute(db, _command(mode="edit"))

    assert result.edit_session_id is not None


def test_viewer_config_rejects_too_large_file() -> None:
    db = MagicMock(spec=Session)
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
        ).execute(db, _command(file_size_limit_bytes=1))

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST
    assert "too large" in exc_info.value.message


def test_viewer_config_rejects_session_owner_mismatch() -> None:
    db = MagicMock(spec=Session)
    storage_service = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeViewerConfigUseCase(
            storage_service=storage_service,
            editing_store=MagicMock(),
        ).execute(db, _command(session_user_id="other-user"))

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN