from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.office_editing_service import OfficeEditSession, OfficeSaveRequest
from app.services.office_writeback_service import (
    OfficeSaveWritebackService,
    OfficeWritebackStateCommitError,
)


def _edit_session(*, manifest_key: str | None = "manifest.json") -> OfficeEditSession:
    return OfficeEditSession(
        edit_session_id="edit-123",
        session_id="session-123",
        user_id="user-123",
        file_path="report.docx",
        object_key="ws/abc/report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        manifest_key=manifest_key,
        document_key="doc-key",
        callback_token="callback-token",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def _save_request() -> OfficeSaveRequest:
    now = datetime.now(UTC)
    return OfficeSaveRequest(
        save_request_id="save-123",
        edit_session_id="edit-123",
        session_id="session-123",
        user_id="user-123",
        file_path="report.docx",
        document_key="doc-key",
        status="committing",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def test_direct_object_state_commit_failure_raises_committed_state_error() -> None:
    storage_service = MagicMock()
    editing_store = MagicMock()
    editing_store.complete_save_request.side_effect = RuntimeError(
        "state commit failed"
    )

    service = OfficeSaveWritebackService(
        storage_service=storage_service,
        editing_store=editing_store,
    )

    with pytest.raises(
        OfficeWritebackStateCommitError,
        match="storage commit succeeded",
    ):
        service.commit_saved_content(
            edit_session=_edit_session(manifest_key=None),
            save_request=_save_request(),
            content=b"new docx bytes",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    storage_service.put_object.assert_called_once_with(
        key="ws/abc/report.docx",
        body=b"new docx bytes",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
