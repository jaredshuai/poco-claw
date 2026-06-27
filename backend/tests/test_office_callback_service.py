import asyncio
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeCallbackRequest
from app.services.office_callback_service import OfficeCallbackUseCase
from tests.office_test_helpers import make_edit_session


def _use_case(*, editing_store: MagicMock) -> OfficeCallbackUseCase:
    return OfficeCallbackUseCase(
        storage_service=MagicMock(),
        editing_store=editing_store,
        validate_download_url=lambda _: None,
    )


def test_callback_rejects_invalid_token() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    editing_store.resolve_by_token.return_value = None

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            _use_case(editing_store=editing_store).handle(
                db,
                token="bad-token",
                callback=OfficeCallbackRequest(status=7, key="doc-key"),
            )
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_callback_rejects_document_key_mismatch() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    editing_store.resolve_by_token.return_value = make_edit_session()

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            _use_case(editing_store=editing_store).handle(
                db,
                token="callback-token",
                callback=OfficeCallbackRequest(status=7, key="other-key"),
            )
        )

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_callback_delegates_status_7_to_save_use_case() -> None:
    db = MagicMock(spec=Session)
    editing_store = MagicMock()
    es = make_edit_session()
    editing_store.resolve_by_token.return_value = es
    editing_store.get_save_request.return_value = MagicMock()
    editing_store.get_save_request.return_value.status = "pending"
    editing_store.get_save_request.return_value.edit_session_id = es.id
    editing_store.get_save_request.return_value.id = uuid.uuid4()

    callback = OfficeCallbackRequest(
        status=7, key=es.document_key, userdata="save-123", error=123
    )

    asyncio.run(
        _use_case(editing_store=editing_store).handle(
            db, token="callback-token", callback=callback
        )
    )

    editing_store.mark_failed.assert_called_once()
