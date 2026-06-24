"""OnlyOffice explicit force-save use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.office_edit_session import OfficeEditSession
from app.models.office_save_request import OfficeSaveRequest
from app.utils.workspace_manifest import normalize_manifest_path


class OfficeForceSaveCommandClient(Protocol):
    async def forcesave(self, *, document_key: str, userdata: str) -> None: ...


class OfficeForceSaveEditingStore(Protocol):
    def get_edit_session(
        self, db: Session, edit_session_id: object
    ) -> OfficeEditSession | None: ...

    def get_active_save_request(
        self,
        db: Session,
        edit_session_id: object,
    ) -> OfficeSaveRequest | None: ...

    def create_save_request(
        self,
        db: Session,
        session: OfficeEditSession,
    ) -> OfficeSaveRequest: ...

    def mark_failed(
        self,
        db: Session,
        save_request_id: object,
        *,
        error_code: str,
        error_message: str | None = None,
    ) -> None: ...

    def mark_saving(self, db: Session, save_request_id: object) -> None: ...


@dataclass(frozen=True)
class OfficeForceSaveCommand:
    session_id: str
    session_user_id: str
    user_id: str
    file_path: str
    edit_session_id: str


@dataclass(frozen=True)
class OfficeForceSaveResult:
    save_request_id: str
    status: Literal["saving"] = "saving"


class OfficeSaveInProgressError(Exception):
    def __init__(self, active_save_request_id: str) -> None:
        self.active_save_request_id = active_save_request_id
        super().__init__("Office save is already in progress")


class OfficeForceSaveUseCase:
    """Create a save request and ask OnlyOffice to force-save the document."""

    def __init__(
        self,
        *,
        editing_store: OfficeForceSaveEditingStore,
        command_client: OfficeForceSaveCommandClient,
    ) -> None:
        self.editing_store = editing_store
        self.command_client = command_client

    async def execute(
        self, db: Session, command: OfficeForceSaveCommand
    ) -> OfficeForceSaveResult:
        if command.session_user_id != command.user_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Session does not belong to the user",
            )

        edit_session = self.editing_store.get_edit_session(
            db, command.edit_session_id
        )
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

        active = self.editing_store.get_active_save_request(
            db, edit_session.edit_session_id
        )
        if active is not None:
            raise OfficeSaveInProgressError(str(active.save_request_id))

        save_request = self.editing_store.create_save_request(db, edit_session)
        try:
            await self.command_client.forcesave(
                document_key=edit_session.document_key,
                userdata=str(save_request.save_request_id),
            )
        except Exception as exc:
            self.editing_store.mark_failed(
                db,
                save_request.save_request_id,
                error_code="office_command_rejected",
                error_message=str(exc),
            )
            raise

        self.editing_store.mark_saving(db, save_request.save_request_id)
        return OfficeForceSaveResult(
            save_request_id=str(save_request.save_request_id)
        )
