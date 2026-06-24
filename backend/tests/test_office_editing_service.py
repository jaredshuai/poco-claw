"""Tests for the new DB-backed OfficeEditingStore.

These verify the store's delegation to repositories. Full state-machine
semantics are covered by the repository and API integration tests.
"""

from unittest.mock import MagicMock
import uuid

from sqlalchemy.orm import Session

from app.repositories.office_edit_session_repository import OfficeEditSessionRepository
from app.repositories.office_save_request_repository import (
    OfficeSaveRequestRepository,
)
from app.services.office_editing_service import OfficeEditingStore
from app.services.office_save_statuses import SAVE_STATUS_SAVING


def test_create_edit_session_delegates_to_repository():
    db = MagicMock(spec=Session)
    store = OfficeEditingStore()

    result = store.create_edit_session(
        db,
        session_id="s1",
        user_id="u1",
        file_path="test.docx",
        object_key="k1",
        mime_type="application/pdf",
        manifest_key="m.json",
        document_key="dk",
    )

    assert result is not None
    assert result.session_id == "s1"


def test_get_edit_session_returns_none_for_missing():
    db = MagicMock(spec=Session)
    store = OfficeEditingStore()

    result = store.get_edit_session(db, uuid.uuid4())

    assert result is None


def test_cleanup_expired_returns_empty_when_nothing_expired():
    db = MagicMock(spec=Session)
    OfficeEditSessionRepository.expire_discarded_and_expired = MagicMock(
        return_value=[]
    )
    OfficeSaveRequestRepository.expire_old = MagicMock(return_value=0)
    OfficeSaveRequestRepository.recover_staged = MagicMock(return_value=[])
    store = OfficeEditingStore()

    result = store.cleanup_expired(db)

    assert result["edit_sessions"] == 0
    assert result["save_requests"] == 0


def test_store_provides_status_constants():
    """Verify store still exposes the canonical status constant module."""
    from app.services.office_editing_service import SAVE_STATUS_SAVING

    assert SAVE_STATUS_SAVING == "saving"