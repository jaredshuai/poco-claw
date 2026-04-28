import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeCallbackRequest
from app.services.office_callback_service import OfficeCallbackUseCase
from app.services.office_editing_service import (
    OfficeEditSession,
    OfficeSaveRequest,
    SAVE_STATUS_SAVING,
)


def _edit_session() -> OfficeEditSession:
    return OfficeEditSession(
        edit_session_id="edit-123",
        session_id="session-123",
        user_id="user-123",
        file_path="report.docx",
        object_key="ws/abc/report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        manifest_key="manifest.json",
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
        status=SAVE_STATUS_SAVING,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _use_case(*, editing_store: MagicMock) -> OfficeCallbackUseCase:
    return OfficeCallbackUseCase(
        storage_service=MagicMock(),
        editing_store=editing_store,
        validate_download_url=lambda _: None,
    )


def test_callback_rejects_invalid_token() -> None:
    editing_store = MagicMock()
    editing_store.resolve_by_token.return_value = None

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            _use_case(editing_store=editing_store).handle(
                token="bad-token",
                callback=OfficeCallbackRequest(status=7, key="doc-key"),
            )
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_callback_rejects_document_key_mismatch() -> None:
    editing_store = MagicMock()
    editing_store.resolve_by_token.return_value = _edit_session()

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            _use_case(editing_store=editing_store).handle(
                token="callback-token",
                callback=OfficeCallbackRequest(status=7, key="other-key"),
            )
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_callback_delegates_status_7_to_save_use_case() -> None:
    editing_store = MagicMock()
    editing_store.resolve_by_token.return_value = _edit_session()
    editing_store.get_save_request.return_value = _save_request()

    asyncio.run(
        _use_case(editing_store=editing_store).handle(
            token="callback-token",
            callback=OfficeCallbackRequest(
                status=7,
                key="doc-key",
                userdata="save-123",
                error=123,
            ),
        )
    )

    editing_store.mark_failed.assert_called_once_with(
        "save-123",
        error_code="office_forcesave_failed",
        error_message="123",
    )
