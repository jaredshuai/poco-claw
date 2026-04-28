from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_editing_service import (
    OfficeSaveRequest,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_SAVING,
)
from app.services.office_save_status_service import (
    OfficeSaveStatusQuery,
    OfficeSaveStatusUseCase,
)


def _save_request(
    *,
    status: str = SAVE_STATUS_SAVING,
    user_id: str = "user-123",
    session_id: str = "session-123",
) -> OfficeSaveRequest:
    now = datetime.now(UTC)
    return OfficeSaveRequest(
        save_request_id="save-123",
        edit_session_id="edit-123",
        session_id=session_id,
        user_id=user_id,
        file_path="docs/report.docx",
        document_key="doc-key",
        status=status,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=5),
        completed_at=now if status == SAVE_STATUS_FAILED else None,
        error_code="writeback_failed" if status == SAVE_STATUS_FAILED else None,
        error_message="boom" if status == SAVE_STATUS_FAILED else None,
    )


def _query(**overrides: str) -> OfficeSaveStatusQuery:
    values = {
        "session_id": "session-123",
        "save_request_id": "save-123",
        "user_id": "user-123",
    }
    values.update(overrides)
    return OfficeSaveStatusQuery(**values)


def test_save_status_returns_failed_when_missing_or_expired() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = None

    result = OfficeSaveStatusUseCase(editing_store=editing_store).execute(_query())

    assert result.save_request_id == "save-123"
    assert result.status == SAVE_STATUS_FAILED
    assert result.error_code == "not_found_or_expired"


def test_save_status_maps_committing_to_saving() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = _save_request(
        status=SAVE_STATUS_COMMITTING
    )

    result = OfficeSaveStatusUseCase(editing_store=editing_store).execute(_query())

    assert result.save_request_id == "save-123"
    assert result.status == SAVE_STATUS_SAVING


def test_save_status_rejects_user_mismatch() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = _save_request(user_id="other-user")

    with pytest.raises(AppException) as exc_info:
        OfficeSaveStatusUseCase(editing_store=editing_store).execute(_query())

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
