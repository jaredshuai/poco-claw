from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_discard_edit_session_service import (
    OfficeDiscardEditSessionCommand,
    OfficeDiscardEditSessionUseCase,
)
from app.services.office_editing_service import OfficeEditSession


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


def _command(**overrides: str) -> OfficeDiscardEditSessionCommand:
    values = {
        "session_id": "session-123",
        "session_user_id": "user-123",
        "user_id": "user-123",
        "file_path": "docs/report.docx",
        "edit_session_id": "edit-123",
    }
    values.update(overrides)
    return OfficeDiscardEditSessionCommand(**values)


def test_discard_edit_session_revokes_session() -> None:
    editing_store = MagicMock()
    editing_store.get_edit_session.return_value = _edit_session()

    result = OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
        _command()
    )

    assert result.edit_session_id == "edit-123"
    assert result.status == "discarded"
    editing_store.discard_edit_session.assert_called_once_with("edit-123")


def test_discard_edit_session_rejects_session_owner_mismatch() -> None:
    editing_store = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
            _command(session_user_id="other-user")
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
    editing_store.get_edit_session.assert_not_called()


def test_discard_edit_session_rejects_mismatched_file() -> None:
    editing_store = MagicMock()
    editing_store.get_edit_session.return_value = _edit_session()

    with pytest.raises(AppException) as exc_info:
        OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
            _command(file_path="docs/other.docx")
        )

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST
    editing_store.discard_edit_session.assert_not_called()
