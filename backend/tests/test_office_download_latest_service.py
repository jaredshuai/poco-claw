from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_download_latest_service import (
    OfficeDownloadLatestCommand,
    OfficeDownloadLatestUseCase,
)


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
        entry["mime_type"] = mime_type
    if size is not None:
        entry["size"] = size
    return entry


def _command(**overrides: str | int | None) -> OfficeDownloadLatestCommand:
    values = {
        "session_id": "session-123",
        "session_user_id": "user-123",
        "user_id": "user-123",
        "file_path": "docs/report.docx",
        "workspace_manifest_key": "manifest.json",
        "workspace_files_prefix": "ws/abc",
        "expires_in": 3600,
    }
    values.update(overrides)
    return OfficeDownloadLatestCommand(**values)


def test_download_latest_presigns_current_workspace_object() -> None:
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
        "etag": "etag-v2",
    }
    storage_service.presign_get.return_value = "https://s3.example.com/report.docx"

    result = OfficeDownloadLatestUseCase(storage_service=storage_service).execute(
        _command()
    )

    assert result.url == "https://s3.example.com/report.docx"
    assert result.file_path == "docs/report.docx"
    assert result.expires_in == 3600
    storage_service.presign_get.assert_called_once_with(
        "ws/abc/docs/report.docx",
        response_content_disposition='attachment; filename="report.docx"',
        response_content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        expires_in=3600,
    )


def test_download_latest_rejects_session_owner_mismatch() -> None:
    storage_service = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeDownloadLatestUseCase(storage_service=storage_service).execute(
            _command(session_user_id="other-user")
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
    storage_service.get_manifest.assert_not_called()


def test_download_latest_rejects_invalid_file_path() -> None:
    storage_service = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeDownloadLatestUseCase(storage_service=storage_service).execute(
            _command(file_path="../report.docx")
        )

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST
    storage_service.get_manifest.assert_not_called()


def test_download_latest_rejects_missing_storage_object() -> None:
    storage_service = MagicMock()
    storage_service.get_manifest.return_value = {
        "files": [_file_entry("docs/report.docx", key="ws/abc/docs/report.docx")]
    }
    storage_service.get_object_metadata.return_value = None

    with pytest.raises(AppException) as exc_info:
        OfficeDownloadLatestUseCase(storage_service=storage_service).execute(_command())

    assert exc_info.value.error_code is ErrorCode.NOT_FOUND
    storage_service.presign_get.assert_not_called()
