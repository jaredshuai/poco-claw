"""OnlyOffice discard edit-session use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.office_edit_session import OfficeEditSession
from app.utils.workspace_manifest import normalize_manifest_path


class OfficeDiscardEditingStore(Protocol):
    def get_edit_session(
        self, db: Session, edit_session_id: object
    ) -> OfficeEditSession | None: ...

    def discard_edit_session(self, db: Session, edit_session_id: object) -> bool: ...


@dataclass(frozen=True)
class OfficeDiscardEditSessionCommand:
    session_id: str
    session_user_id: str
    user_id: str
    file_path: str
    edit_session_id: str


@dataclass(frozen=True)
class OfficeDiscardEditSessionResult:
    edit_session_id: str
    status: Literal["discarded"] = "discarded"


class OfficeDiscardEditSessionUseCase:
    """Discard an Office edit session after ownership checks."""

    def __init__(self, *, editing_store: OfficeDiscardEditingStore) -> None:
        self.editing_store = editing_store

    def execute(
        self,
        db: Session,
        command: OfficeDiscardEditSessionCommand,
    ) -> OfficeDiscardEditSessionResult:
        if command.session_user_id != command.user_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Session does not belong to the user",
            )

        edit_session = self.editing_store.get_edit_session(db, command.edit_session_id)
        if (
            edit_session is None
            or edit_session.session_id != command.session_id
            or normalize_manifest_path(edit_session.file_path)
            != normalize_manifest_path(command.file_path)
            or edit_session.user_id != command.user_id
        ):
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Invalid or expired Office edit session",
            )

        self.editing_store.discard_edit_session(db, edit_session.edit_session_id)
        return OfficeDiscardEditSessionResult(
            edit_session_id=str(edit_session.edit_session_id),
        )
