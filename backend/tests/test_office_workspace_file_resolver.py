from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_workspace_file_resolver import (
    OfficeWorkspaceFileQuery,
    OfficeWorkspaceFileResolver,
)


def test_resolver_returns_manifest_file_metadata() -> None:
    storage_service = MagicMock()
    storage_service.get_manifest.return_value = {
        "files": [
            {
                "path": "docs/report.docx",
                "key": "ws/abc/docs/report.docx",
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size": "2048",
            }
        ]
    }

    result = OfficeWorkspaceFileResolver(storage_service=storage_service).resolve(
        OfficeWorkspaceFileQuery(
            manifest_key="manifest.json",
            files_prefix="ws/abc",
            file_path="docs/report.docx",
        )
    )

    assert result.object_key == "ws/abc/docs/report.docx"
    assert result.mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert result.file_size == 2048


def test_resolver_falls_back_to_workspace_prefix() -> None:
    storage_service = MagicMock()
    storage_service.get_manifest.return_value = {
        "files": [{"path": "docs/report.docx"}]
    }

    result = OfficeWorkspaceFileResolver(storage_service=storage_service).resolve(
        OfficeWorkspaceFileQuery(
            manifest_key="manifest.json",
            files_prefix="ws/abc",
            file_path="docs/report.docx",
        )
    )

    assert result.object_key == "ws/abc/docs/report.docx"


def test_resolver_rejects_key_escaping_workspace_prefix() -> None:
    storage_service = MagicMock()
    storage_service.get_manifest.return_value = {
        "files": [
            {
                "path": "docs/report.docx",
                "key": "ws/other/docs/report.docx",
            }
        ]
    }

    with pytest.raises(AppException) as exc_info:
        OfficeWorkspaceFileResolver(storage_service=storage_service).resolve(
            OfficeWorkspaceFileQuery(
                manifest_key="manifest.json",
                files_prefix="ws/abc",
                file_path="docs/report.docx",
            )
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_resolver_rejects_missing_manifest_key() -> None:
    storage_service = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeWorkspaceFileResolver(storage_service=storage_service).resolve(
            OfficeWorkspaceFileQuery(
                manifest_key=None,
                files_prefix="ws/abc",
                file_path="docs/report.docx",
            )
        )

    assert exc_info.value.error_code is ErrorCode.NOT_FOUND
    storage_service.get_manifest.assert_not_called()
