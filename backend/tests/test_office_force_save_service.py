import asyncio
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_force_save_service import (
    OfficeForceSaveCommand,
    OfficeForceSaveUseCase,
    OfficeSaveInProgressError,
)
from tests.office_test_helpers import make_edit_session, make_save_request


def _command(**overrides: str) -> OfficeForceSaveCommand:
    values = {
        "session_id": "session-123",
        "session_user_id": "user-1",
        "user_id": "user-1",
        "file_path": "report.docx",
        "edit_session_id": str(uuid.uuid4()),
    }
    values.update(overrides)
    return OfficeForceSaveCommand(**values)


def test_force_save_creates_request_and_marks_saving() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    command_client = MagicMock()
    command_client.forcesave = AsyncMock(return_value=None)
    es = make_edit_session()
    editing_store.get_edit_session.return_value = es
    editing_store.get_active_save_request.return_value = None
    sr = make_save_request(edit_session_id=es.id)
    editing_store.create_save_request.return_value = sr

    result = asyncio.run(
        OfficeForceSaveUseCase(
            editing_store=editing_store, command_client=command_client
        ).execute(db, _command(edit_session_id=str(es.id)))
    )

    assert result.status == "saving"
    command_client.forcesave.assert_awaited_once_with(
        document_key=es.document_key, userdata=str(sr.id)
    )
    editing_store.mark_saving.assert_called_once_with(db, sr.id)


def test_force_save_rejects_active_save_request() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    command_client = MagicMock()
    es = make_edit_session()
    editing_store.get_edit_session.return_value = es
    editing_store.get_active_save_request.return_value = make_save_request(
        edit_session_id=es.id
    )

    with pytest.raises(OfficeSaveInProgressError):
        asyncio.run(
            OfficeForceSaveUseCase(
                editing_store=editing_store, command_client=command_client
            ).execute(db, _command(edit_session_id=str(es.id)))
        )

    editing_store.create_save_request.assert_not_called()


def test_force_save_marks_request_failed_when_command_rejected() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    command_client = MagicMock()
    command_client.forcesave = AsyncMock(side_effect=RuntimeError("boom"))
    es = make_edit_session()
    editing_store.get_edit_session.return_value = es
    editing_store.get_active_save_request.return_value = None
    sr = make_save_request(edit_session_id=es.id)
    editing_store.create_save_request.return_value = sr

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            OfficeForceSaveUseCase(
                editing_store=editing_store, command_client=command_client
            ).execute(db, _command(edit_session_id=str(es.id)))
        )

    editing_store.mark_failed.assert_called_once_with(
        db, sr.id, error_code="office_command_rejected", error_message="boom"
    )


def test_force_save_rejects_session_owner_mismatch() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    command_client = MagicMock()

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            OfficeForceSaveUseCase(
                editing_store=editing_store, command_client=command_client
            ).execute(db, _command(session_user_id="other-user"))
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
    editing_store.get_edit_session.assert_not_called()
