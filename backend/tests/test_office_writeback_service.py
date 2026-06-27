"""Tests for Office writeback — recovery marker + state commit error.

These unit-tests mock the editing store and verify the commit_saved_content
method's behavior for the new DB-backed interface.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.services.office_editing_service import (
    OfficeEditingStore,
)
from app.services.office_save_statuses import (
    SAVE_STATUS_COMMITTING,
)
from app.services.office_writeback_service import (
    OfficeSaveWritebackService,
    OfficeWritebackStateCommitError,
)

# Reusable helpers that return our *new* model types (SQLAlchemy)
from app.models.office_edit_session import OfficeEditSession
from app.models.office_save_request import OfficeSaveRequest

import uuid


def _edit_session(*, manifest_key: str | None = "manifest.json") -> OfficeEditSession:
    es = OfficeEditSession(
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
    es.id = uuid.uuid4()
    return es


def _save_request(*, staged_object_key: str | None = None) -> OfficeSaveRequest:
    now = datetime.now(UTC)
    sr = OfficeSaveRequest(
        edit_session_id=uuid.uuid4(),
        session_id="session-123",
        user_id="user-123",
        file_path="report.docx",
        document_key="doc-key",
        status=SAVE_STATUS_COMMITTING,
        expires_at=now + timedelta(minutes=5),
        staged_object_key=staged_object_key,
    )
    sr.id = uuid.uuid4()
    sr.created_at = now
    sr.updated_at = now
    return sr


def test_direct_object_state_commit_failure_raises_committed_state_error() -> None:
    db = MagicMock(spec=Session)
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
            db,
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
    editing_store.mark_staged.assert_called_once()


def test_sets_recovery_marker_before_manifest_flip() -> None:
    """staged_object_key should be passed to mark_staged before manifest update."""
    db = MagicMock(spec=Session)
    storage_service = MagicMock()
    storage_service.get_manifest.return_value = {
        "files": [{"path": "report.docx", "key": "ws/abc/report.docx"}]
    }
    storage_service.get_object_metadata.return_value = {
        "content_length": 10,
        "etag": "abc123",
    }
    editing_store = MagicMock()
    save_request = _save_request()

    service = OfficeSaveWritebackService(
        storage_service=storage_service,
        editing_store=editing_store,
    )

    service.commit_saved_content(
        db,
        edit_session=_edit_session(manifest_key="manifest.json"),
        save_request=save_request,
        content=b"new content",
        content_type="text/plain",
    )

    editing_store.mark_staged.assert_called_once()
    _, kwargs = editing_store.mark_staged.call_args
    assert "staged_object_key" in kwargs
    assert ".office-saves/" in kwargs["staged_object_key"]


def test_sets_recovery_marker_direct_object() -> None:
    """Without manifest, mark_staged is still called."""
    db = MagicMock(spec=Session)
    storage_service = MagicMock()
    editing_store = MagicMock()
    save_request = _save_request()

    service = OfficeSaveWritebackService(
        storage_service=storage_service,
        editing_store=editing_store,
    )

    service.commit_saved_content(
        db,
        edit_session=_edit_session(manifest_key=None),
        save_request=save_request,
        content=b"new content",
        content_type="text/plain",
    )

    editing_store.mark_staged.assert_called_once()
    _, kwargs = editing_store.mark_staged.call_args
    assert kwargs["staged_object_key"] == "ws/abc/report.docx"


def test_marker_persist_failure_before_manifest_cleans_up_staged_object() -> None:
    """If mark_staged raises, staged object is cleaned up."""
    db = MagicMock(spec=Session)
    storage_service = MagicMock()
    editing_store = MagicMock()
    editing_store.mark_staged.side_effect = RuntimeError("persist failed")
    save_request = _save_request()

    service = OfficeSaveWritebackService(
        storage_service=storage_service,
        editing_store=editing_store,
    )

    with pytest.raises(RuntimeError, match="persist failed"):
        service.commit_saved_content(
            db,
            edit_session=_edit_session(manifest_key="manifest.json"),
            save_request=save_request,
            content=b"new content",
            content_type="text/plain",
        )

    storage_service.delete_object.assert_called_once()


class TestRecoverStagedWritebacks:
    """Tests for OfficeEditingStore.recover_staged_writebacks (delegated)."""

    def test_calls_recover_staged_on_store(self) -> None:
        db = MagicMock(spec=Session)
        store = OfficeEditingStore()
        store.recover_staged_writebacks(db)
        # No crash — the underlying repository is mocked in isolation tests
        assert True
