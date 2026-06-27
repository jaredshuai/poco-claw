"""Shared test helpers for Office tests.

Provides factory functions that construct the new SQLAlchemy model instances
the way the old dataclass factories did, so all test files can migrate easily.
Also provides StatefulOfficeEditingStore, a mock that maintains in-memory
state so tests can exercise the full create→callback→status flow without a DB.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.office_edit_session import OfficeEditSession
from app.models.office_save_request import OfficeSaveRequest
from app.services.office_save_statuses import (
    ACTIVE_SAVE_STATUSES,
    SAVE_STATUS_CALLBACK_RECEIVED,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_STAGED,
)


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


def _uuid_key(v) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


class StatefulOfficeEditingStore:
    """In-memory mock of OfficeEditingStore that maintains state across calls.

    This avoids the complexity of a real DB session in integration tests while
    still exercising the full create→callback→status flow. Each method mirrors
    the real store's signature (db is accepted but ignored).
    """

    def __init__(self) -> None:
        self._sessions: dict[Any, OfficeEditSession] = {}
        self._tokens: dict[str, Any] = {}
        self._save_requests: dict[Any, OfficeSaveRequest] = {}

    # --- Edit sessions --- #

    def create_edit_session(self, db, **kw) -> OfficeEditSession:
        import secrets as _secrets

        es = make_edit_session(
            session_id=str(kw.get("session_id", "s1")),
            user_id=str(kw.get("user_id", "user-1")),
            file_path=str(kw.get("file_path", "report.docx")),
            object_key=str(kw.get("object_key", "ws/abc/report.docx")),
            mime_type=kw.get("mime_type"),
            manifest_key=kw.get("manifest_key"),
            document_key=str(kw.get("document_key", "dk")),
            callback_token=_secrets.token_urlsafe(16),
        )
        if kw.get("edit_session_id"):
            es.id = uuid.UUID(str(kw["edit_session_id"]))
        self._sessions[es.id] = es
        self._tokens[es.callback_token] = es.id
        return es

    def get_edit_session(self, db, edit_session_id) -> OfficeEditSession | None:
        es = self._sessions.get(_uuid_key(edit_session_id))
        if es is None or es.discarded:
            return None
        return es

    def discard_edit_session(self, db, edit_session_id) -> bool:
        es = self._sessions.get(_uuid_key(edit_session_id))
        if es is None or es.discarded:
            return False
        es.discarded = True
        self._tokens.pop(es.callback_token, None)
        return True

    def update_edit_session_object_key(self, db, edit_session_id, object_key) -> bool:
        es = self._sessions.get(_uuid_key(edit_session_id))
        if es is None or es.discarded:
            return False
        es.object_key = object_key
        return True

    def resolve_by_token(self, db, token) -> OfficeEditSession | None:
        es_id = self._tokens.get(token)
        if es_id is None:
            return None
        return self.get_edit_session(db, es_id)

    # --- Save requests --- #

    def create_save_request(self, db, session) -> OfficeSaveRequest:
        sr = make_save_request(
            edit_session_id=session.id,
            session_id=session.session_id,
            user_id=session.user_id,
            file_path=session.file_path,
            document_key=session.document_key,
            status=SAVE_STATUS_PENDING,
        )
        self._save_requests[sr.id] = sr
        return sr

    def get_active_save_request(self, db, edit_session_id) -> OfficeSaveRequest | None:
        es_key = _uuid_key(edit_session_id)
        for sr in self._save_requests.values():
            if sr.edit_session_id == es_key and sr.status in ACTIVE_SAVE_STATUSES:
                return sr
        return None

    def get_save_request(self, db, save_request_id) -> OfficeSaveRequest | None:
        sr = self._save_requests.get(_uuid_key(save_request_id))
        if sr and sr.status in {SAVE_STATUS_STAGED, SAVE_STATUS_COMMITTING}:
            # Auto-recover like the real store's cleanup_expired does
            sr.status = SAVE_STATUS_SAVED
            sr.completed_at = datetime.now(UTC)
            if sr.staged_object_key:
                es = self._sessions.get(sr.edit_session_id)
                if es and not es.discarded:
                    es.object_key = sr.staged_object_key
        return sr

    def mark_saving(self, db, save_request_id) -> None:
        sr = self._save_requests.get(_uuid_key(save_request_id))
        if sr:
            sr.status = SAVE_STATUS_SAVING

    def mark_staged(self, db, save_request_id, *, staged_object_key=None) -> None:
        sr = self._save_requests.get(_uuid_key(save_request_id))
        if sr:
            sr.status = SAVE_STATUS_STAGED
            if staged_object_key:
                sr.staged_object_key = staged_object_key

    def try_begin_commit(self, db, save_request_id, *, edit_session_id):
        sr = self._save_requests.get(_uuid_key(save_request_id))
        es_key = _uuid_key(edit_session_id)
        if (
            sr is None
            or sr.edit_session_id != es_key
            or sr.status not in {SAVE_STATUS_PENDING, SAVE_STATUS_SAVING}
        ):
            return None
        sr.status = SAVE_STATUS_CALLBACK_RECEIVED
        return sr

    def complete_save_request(
        self, db, save_request_id, *, edit_session_id, object_key=None
    ) -> None:
        sr = self._save_requests.get(_uuid_key(save_request_id))
        if sr is None:
            return
        sr.status = SAVE_STATUS_SAVED
        sr.completed_at = datetime.now(UTC)
        if object_key:
            es = self._sessions.get(_uuid_key(edit_session_id))
            if es and not es.discarded:
                es.object_key = object_key

    def mark_saved(self, db, save_request_id) -> None:
        sr = self._save_requests.get(_uuid_key(save_request_id))
        if sr:
            sr.status = SAVE_STATUS_SAVED
            sr.completed_at = datetime.now(UTC)

    def mark_failed(
        self, db, save_request_id, *, error_code, error_message=None
    ) -> None:
        sr = self._save_requests.get(_uuid_key(save_request_id))
        if sr:
            sr.status = SAVE_STATUS_FAILED
            sr.completed_at = datetime.now(UTC)
            sr.error_code = error_code
            sr.error_message = error_message

    def cleanup_expired(self, db, *, now=None) -> dict:
        return {"edit_sessions": 0, "save_requests": 0}

    def recover_staged_writebacks(self, db) -> int:
        return 0
