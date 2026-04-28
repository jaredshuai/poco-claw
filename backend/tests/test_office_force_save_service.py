import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_editing_service import (
    OfficeEditSession,
    OfficeSaveRequest,
    SAVE_STATUS_SAVING,
)
from app.services.office_force_save_service import (
    OfficeForceSaveCommand,
    OfficeForceSaveUseCase,
    OfficeSaveInProgressError,
)


def _edit_session() -> OfficeEditSession:
    return OfficeEditSession(
        edit_session_id="edit-123",
        session_id="session-123",
        user_id="user-123",
        file_path="docs/report.docx",
        object_key="ws/abc/docs/report.docx",
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
        file_path="docs/report.docx",
        document_key="doc-key",
        status="pending",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _command(**overrides: str) -> OfficeForceSaveCommand:
    values = {
        "session_id": "session-123",
        "session_user_id": "user-123",
        "user_id": "user-123",
        "file_path": "docs/report.docx",
        "edit_session_id": "edit-123",
    }
    values.update(overrides)
    return OfficeForceSaveCommand(**values)


def _use_case(
    *, editing_store: MagicMock, command_client: MagicMock
) -> OfficeForceSaveUseCase:
    return OfficeForceSaveUseCase(
        editing_store=editing_store,
        command_client=command_client,
    )


def test_force_save_creates_request_and_marks_saving() -> None:
    editing_store = MagicMock()
    command_client = MagicMock()
    command_client.forcesave = AsyncMock(return_value=None)
    editing_store.get_edit_session.return_value = _edit_session()
    editing_store.get_active_save_request.return_value = None
    editing_store.create_save_request.return_value = _save_request()

    result = asyncio.run(
        _use_case(
            editing_store=editing_store,
            command_client=command_client,
        ).execute(_command())
    )

    assert result.save_request_id == "save-123"
    assert result.status == SAVE_STATUS_SAVING
    command_client.forcesave.assert_awaited_once_with(
        document_key="doc-key",
        userdata="save-123",
    )
    editing_store.mark_saving.assert_called_once_with("save-123")


def test_force_save_rejects_active_save_request() -> None:
    editing_store = MagicMock()
    command_client = MagicMock()
    editing_store.get_edit_session.return_value = _edit_session()
    editing_store.get_active_save_request.return_value = _save_request()

    with pytest.raises(OfficeSaveInProgressError) as exc_info:
        asyncio.run(
            _use_case(
                editing_store=editing_store,
                command_client=command_client,
            ).execute(_command())
        )

    assert exc_info.value.active_save_request_id == "save-123"
    editing_store.create_save_request.assert_not_called()


def test_force_save_marks_request_failed_when_command_rejected() -> None:
    editing_store = MagicMock()
    command_client = MagicMock()
    command_client.forcesave = AsyncMock(side_effect=RuntimeError("boom"))
    editing_store.get_edit_session.return_value = _edit_session()
    editing_store.get_active_save_request.return_value = None
    editing_store.create_save_request.return_value = _save_request()

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            _use_case(
                editing_store=editing_store,
                command_client=command_client,
            ).execute(_command())
        )

    editing_store.mark_failed.assert_called_once_with(
        "save-123",
        error_code="office_command_rejected",
        error_message="boom",
    )
    editing_store.mark_saving.assert_not_called()


def test_force_save_rejects_session_owner_mismatch() -> None:
    editing_store = MagicMock()
    command_client = MagicMock()

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            _use_case(
                editing_store=editing_store,
                command_client=command_client,
            ).execute(_command(session_user_id="other-user"))
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
    editing_store.get_edit_session.assert_not_called()
