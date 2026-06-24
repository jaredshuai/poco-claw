import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_editing_service import (
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
)
from app.services.office_callback_save_service import OfficeCallbackSaveUseCase
from app.schemas.office import OfficeCallbackRequest
from tests.office_test_helpers import make_edit_session, make_save_request


def _use_case(*, editing_store: MagicMock) -> OfficeCallbackSaveUseCase:
    return OfficeCallbackSaveUseCase(
        storage_service=MagicMock(),
        editing_store=editing_store,
        validate_download_url=lambda _: None,
    )


def test_failed_callback_marks_active_save_request_failed() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    edit_session = make_edit_session()
    sr = make_save_request(
        status=SAVE_STATUS_SAVING,
        edit_session_id=edit_session.id,
    )
    editing_store.get_save_request.return_value = sr
    callback = OfficeCallbackRequest(
        status=7, key="doc-key", userdata=str(sr.id), error=123
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle_failed_callback(
            db, edit_session=edit_session, callback=callback
        )
    )

    editing_store.mark_failed.assert_called_once_with(
        db, sr.id, error_code="office_forcesave_failed", error_message="123"
    )


def test_handle_callback_dispatches_failed_status() -> None:
    use_case = _use_case(editing_store=MagicMock())
    use_case.handle_failed_callback = AsyncMock(return_value=None)
    callback = OfficeCallbackRequest(status=7, key="doc-key", userdata="save-123")
    edit_session = make_edit_session()
    db = MagicMock(spec=Session)

    asyncio.run(
        use_case.handle_callback(
            db,
            edit_session=edit_session,
            callback=callback,
        )
    )

    use_case.handle_failed_callback.assert_awaited_once_with(
        db, edit_session=edit_session, callback=callback
    )


def test_failed_callback_ignores_terminal_save_request() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = make_save_request(
        status=SAVE_STATUS_SAVED
    )
    callback = OfficeCallbackRequest(
        status=7, key="doc-key", userdata="save-123", error=123
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle_failed_callback(
            db, edit_session=make_edit_session(), callback=callback
        )
    )

    editing_store.mark_failed.assert_not_called()


def test_failed_callback_ignores_other_edit_session() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    editing_store.get_save_request.return_value = make_save_request(
        status=SAVE_STATUS_SAVING
    )
    callback = OfficeCallbackRequest(
        status=7, key="doc-key", userdata="save-123", error=123
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle_failed_callback(
            db,
            edit_session=make_edit_session(),
            callback=callback,
        )
    )

    editing_store.mark_failed.assert_not_called()