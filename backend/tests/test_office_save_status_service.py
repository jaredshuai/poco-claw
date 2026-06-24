from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.office_save_request import OfficeSaveRequest
from app.services.office_editing_service import (
    SAVE_STATUS_CALLBACK_RECEIVED,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_STAGED,
)
from app.services.office_save_status_service import (
    OfficeSaveStatusQuery,
    OfficeSaveStatusUseCase,
)


def _save_request(status: str = SAVE_STATUS_SAVING) -> OfficeSaveRequest:
    now = datetime.now(UTC)
    sr = OfficeSaveRequest(
        edit_session_id=uuid.uuid4(),
        session_id="session-123",
        user_id="user-123",
        file_path="report.docx",
        document_key="dk",
        status=status,
        expires_at=now + timedelta(minutes=5),
    )
    sr.id = uuid.uuid4()
    sr.created_at = now
    sr.updated_at = now
    return sr


def _query() -> OfficeSaveStatusQuery:
    return OfficeSaveStatusQuery(
        session_id="session-123",
        save_request_id="save-123",
        user_id="user-123",
    )


def test_save_status_returns_failed_when_missing_or_expired() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = None

    result = OfficeSaveStatusUseCase(editing_store=editing_store).execute(
        MagicMock(spec=Session), _query()
    )

    assert result.save_request_id == "save-123"
    assert result.status == SAVE_STATUS_FAILED
    assert result.error_code == "not_found_or_expired"


def test_save_status_maps_intermediate_statuses_to_saving() -> None:
    for status in [
        SAVE_STATUS_CALLBACK_RECEIVED,
        SAVE_STATUS_STAGED,
        SAVE_STATUS_COMMITTING,
    ]:
        editing_store = MagicMock()
        sr = _save_request(status=status)
        editing_store.get_save_request.return_value = sr

        result = OfficeSaveStatusUseCase(editing_store=editing_store).execute(
            MagicMock(spec=Session), _query()
        )

        assert result.save_request_id == str(sr.id)
        assert result.status == SAVE_STATUS_SAVING, f"{status} should map to saving"


def test_save_status_rejects_user_mismatch() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = _save_request()

    with pytest.raises(AppException) as exc_info:
        OfficeSaveStatusUseCase(editing_store=editing_store).execute(
            MagicMock(spec=Session),
            OfficeSaveStatusQuery(
                session_id="session-123",
                save_request_id="save-123",
                user_id="other-user",
            ),
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN