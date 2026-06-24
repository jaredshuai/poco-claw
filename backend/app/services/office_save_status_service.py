"""OnlyOffice save status query use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.office_save_request import OfficeSaveRequest
from app.services.office_editing_service import (
    SAVE_STATUS_CALLBACK_RECEIVED,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_STAGED,
)

OfficeSaveStatusValue = Literal["pending", "saving", "saved", "failed"]


class OfficeSaveStatusEditingStore(Protocol):
    def get_save_request(
        self, db: Session, save_request_id: object
    ) -> OfficeSaveRequest | None: ...


@dataclass(frozen=True)
class OfficeSaveStatusQuery:
    session_id: str
    save_request_id: str
    user_id: str


@dataclass(frozen=True)
class OfficeSaveStatusResult:
    save_request_id: str
    status: OfficeSaveStatusValue
    error_code: str | None = None
    error_message: str | None = None
    completed_at: str | None = None


class OfficeSaveStatusUseCase:
    """Return frontend-safe save status for a short-lived save request."""

    def __init__(self, *, editing_store: OfficeSaveStatusEditingStore) -> None:
        self.editing_store = editing_store

    def execute(
        self,
        db: Session,
        query: OfficeSaveStatusQuery,
    ) -> OfficeSaveStatusResult:
        save_request = self.editing_store.get_save_request(db, query.save_request_id)
        if save_request is None or save_request.session_id != query.session_id:
            return OfficeSaveStatusResult(
                save_request_id=query.save_request_id,
                status=SAVE_STATUS_FAILED,
                error_code="not_found_or_expired",
            )

        if save_request.user_id != query.user_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Save request does not belong to the user",
            )

        return OfficeSaveStatusResult(
            save_request_id=str(save_request.save_request_id),
            status=_to_response_status(save_request.status),
            error_code=save_request.error_code,
            error_message=save_request.error_message,
            completed_at=save_request.completed_at.isoformat()
            if save_request.completed_at
            else None,
        )


def _to_response_status(status: str) -> OfficeSaveStatusValue:
    if status in {SAVE_STATUS_CALLBACK_RECEIVED, SAVE_STATUS_STAGED, SAVE_STATUS_COMMITTING}:
        return SAVE_STATUS_SAVING
    if status == SAVE_STATUS_SAVED:
        return SAVE_STATUS_SAVED
    if status == SAVE_STATUS_FAILED:
        return SAVE_STATUS_FAILED
    if status == SAVE_STATUS_PENDING:
        return SAVE_STATUS_PENDING
    return SAVE_STATUS_SAVING
