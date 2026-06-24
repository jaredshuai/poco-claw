"""Shared test helpers for Office tests.

Provides factory functions that construct the new SQLAlchemy model instances
the way the old dataclass factories did, so all test files can migrate easily.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models.office_edit_session import OfficeEditSession
from app.models.office_save_request import OfficeSaveRequest
from app.services.office_save_statuses import SAVE_STATUS_COMMITTING


def make_edit_session(**overrides: object) -> OfficeEditSession:
    """Build an OfficeEditSession model instance with sensible defaults."""
    es = OfficeEditSession(
        session_id="session-123",
        user_id="user-1",
        file_path="report.docx",
        object_key="ws/abc/report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        manifest_key="manifest.json",
        document_key="doc-key",
        callback_token="callback-token",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    es.id = uuid.uuid4()
    for k, v in overrides.items():
        if k == "edit_session_id":
            es.id = uuid.UUID(v) if isinstance(v, str) else v
        else:
            setattr(es, k, v)
    return es


def make_save_request(**overrides: object) -> OfficeSaveRequest:
    """Build an OfficeSaveRequest model instance with sensible defaults."""
    now = datetime.now(UTC)
    edit_session_id = overrides.get("edit_session_id", uuid.uuid4())
    if isinstance(edit_session_id, str):
        edit_session_id = uuid.UUID(edit_session_id)
    sr = OfficeSaveRequest(
        edit_session_id=edit_session_id,
        session_id="session-123",
        user_id="user-123",
        file_path="docs/report.docx",
        document_key="doc-key",
        status=SAVE_STATUS_COMMITTING,
        expires_at=now + timedelta(minutes=5),
    )
    sr.id = uuid.uuid4()
    sr.created_at = now
    sr.updated_at = now
    for k, v in overrides.items():
        if k == "save_request_id":
            sr.id = uuid.UUID(v) if isinstance(v, str) else v
        elif k == "edit_session_id":
            sr.edit_session_id = uuid.UUID(v) if isinstance(v, str) else v
        else:
            setattr(sr, k, v)
    return sr