import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.schemas.office import OfficeCallbackRequest
from app.services.office_callback_save_service import OfficeCallbackSaveUseCase
from app.services.office_editing_service import (
    OfficeEditSession,
    OfficeSaveRequest,
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
)


def _edit_session(*, edit_session_id: str = "edit-123") -> OfficeEditSession:
    return OfficeEditSession(
        edit_session_id=edit_session_id,
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


def _save_request(*, status: str = SAVE_STATUS_SAVING) -> OfficeSaveRequest:
    now = datetime.now(UTC)
    return OfficeSaveRequest(
        save_request_id="save-123",
        edit_session_id="edit-123",
        session_id="session-123",
        user_id="user-123",
        file_path="report.docx",
        document_key="doc-key",
        status=status,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _use_case(*, editing_store: MagicMock) -> OfficeCallbackSaveUseCase:
    return OfficeCallbackSaveUseCase(
        storage_service=MagicMock(),
        editing_store=editing_store,
        validate_download_url=lambda _: None,
    )


def test_failed_callback_marks_active_save_request_failed() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = _save_request()
    callback = OfficeCallbackRequest(
        status=7,
        key="doc-key",
        userdata="save-123",
        error=123,
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle_failed_callback(
            edit_session=_edit_session(),
            callback=callback,
        )
    )

    editing_store.mark_failed.assert_called_once_with(
        "save-123",
        error_code="office_forcesave_failed",
        error_message="123",
    )


def test_failed_callback_ignores_terminal_save_request() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = _save_request(
        status=SAVE_STATUS_SAVED
    )
    callback = OfficeCallbackRequest(
        status=7,
        key="doc-key",
        userdata="save-123",
        error=123,
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle_failed_callback(
            edit_session=_edit_session(),
            callback=callback,
        )
    )

    editing_store.mark_failed.assert_not_called()


def test_failed_callback_ignores_other_edit_session() -> None:
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = _save_request()
    callback = OfficeCallbackRequest(
        status=7,
        key="doc-key",
        userdata="save-123",
        error=123,
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle_failed_callback(
            edit_session=_edit_session(edit_session_id="other-edit"),
            callback=callback,
        )
    )

    editing_store.mark_failed.assert_not_called()
