"""OnlyOffice callback use case."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeCallbackRequest
from app.services.office_callback_save_service import OfficeCallbackSaveUseCase


class OfficeCallbackUseCase:
    """Validate callback session ownership and route save-related statuses."""

    def __init__(
        self,
        *,
        storage_service: Any,
        editing_store: Any,
        validate_download_url: Callable[[str], None],
    ) -> None:
        self.storage_service = storage_service
        self.editing_store = editing_store
        self.validate_download_url = validate_download_url

    async def handle(self, *, token: str, callback: OfficeCallbackRequest) -> None:
        edit_session = self.editing_store.resolve_by_token(token)
        if edit_session is None:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Invalid Office callback token",
            )
        if callback.key != edit_session.document_key:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Office callback document key mismatch",
            )

        await OfficeCallbackSaveUseCase(
            storage_service=self.storage_service,
            editing_store=self.editing_store,
            validate_download_url=self.validate_download_url,
        ).handle_callback(
            edit_session=edit_session,
            callback=callback,
        )
