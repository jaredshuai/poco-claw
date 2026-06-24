from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_discard_edit_session_service import (
    OfficeDiscardEditSessionCommand,
    OfficeDiscardEditSessionUseCase,
)
from tests.office_test_helpers import make_edit_session


def _command(**overrides: str) -> OfficeDiscardEditSessionCommand:
    values = {
        "session_id": "session-123",
        "session_user_id": "user-1",
        "user_id": "user-1",
        "file_path": "report.docx",
        "edit_session_id": str(uuid.uuid4()),
    }
    values.update(overrides)
    return OfficeDiscardEditSessionCommand(**values)


def test_discard_edit_session_revokes_session() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    es = make_edit_session()
    editing_store.get_edit_session.return_value = es

    result = OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
        db, _command(edit_session_id=str(es.id))
    )

    assert result.status == "discarded"
    editing_store.discard_edit_session.assert_called_once_with(db, es.id)


def test_discard_edit_session_rejects_session_owner_mismatch() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()

    with pytest.raises(AppException) as exc_info:
        OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
            db, _command(session_user_id="other-user")
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
    editing_store.get_edit_session.assert_not_called()


def test_discard_edit_session_rejects_mismatched_file() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    editing_store.get_edit_session.return_value = make_edit_session()

    with pytest.raises(AppException) as exc_info:
        OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
            db, _command(file_path="docs/other.docx")
        )

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST
    editing_store.discard_edit_session.assert_not_called()