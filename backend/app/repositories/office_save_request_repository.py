"""Data access for office save requests."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.office_save_request import OfficeSaveRequest
from app.services.office_save_statuses import (
    ACTIVE_SAVE_STATUSES,
    SAVE_STATUS_CALLBACK_RECEIVED,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_STAGED,
)


class OfficeSaveRequestRepository:
    """Data access layer for OnlyOffice force-save lifecycle rows."""

    @staticmethod
    def create(
        session_db: Session,
        *,
        edit_session_id: uuid.UUID,
        session_id: str,
        user_id: str,
        file_path: str,
        document_key: str,
        expires_at: datetime,
        save_request_id: uuid.UUID | None = None,
    ) -> OfficeSaveRequest:
        save_request = OfficeSaveRequest(
            edit_session_id=edit_session_id,
            session_id=session_id,
            user_id=user_id,
            file_path=file_path,
            document_key=document_key,
            status=SAVE_STATUS_PENDING,
            expires_at=expires_at,
        )
        if save_request_id is not None:
            save_request.id = save_request_id
        session_db.add(save_request)
        return save_request

    @staticmethod
    def get_by_id(
        session_db: Session, save_request_id: uuid.UUID
    ) -> OfficeSaveRequest | None:
        return (
            session_db.query(OfficeSaveRequest)
            .filter(OfficeSaveRequest.id == save_request_id)
            .first()
        )

    @staticmethod
    def get_active_by_edit_session(
        session_db: Session, edit_session_id: uuid.UUID
    ) -> OfficeSaveRequest | None:
        return (
            session_db.query(OfficeSaveRequest)
            .filter(OfficeSaveRequest.edit_session_id == edit_session_id)
            .filter(OfficeSaveRequest.status.in_(ACTIVE_SAVE_STATUSES))
            .order_by(OfficeSaveRequest.created_at.desc())
            .first()
        )

    @staticmethod
    def mark_saving(
        session_db: Session, save_request_id: uuid.UUID
    ) -> None:
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.id == save_request_id)
            .values(status=SAVE_STATUS_SAVING, error_code=None, error_message=None)
        )
        session_db.execute(stmt)

    @staticmethod
    def mark_staged(
        session_db: Session,
        save_request_id: uuid.UUID,
        staged_object_key: str,
    ) -> None:
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.id == save_request_id)
            .values(
                status=SAVE_STATUS_STAGED,
                staged_object_key=staged_object_key,
            )
        )
        session_db.execute(stmt)

    @staticmethod
    def try_begin_commit(
        session_db: Session,
        save_request_id: uuid.UUID,
        edit_session_id: uuid.UUID,
    ) -> OfficeSaveRequest | None:
        """Atomically claim a save for writeback.

        Moves a pending/saving save_request to callback_received. Returns the
        updated row on success, None if another caller already claimed it or
        the save_request is no longer eligible (terminal or mismatched).
        """
        eligible = {SAVE_STATUS_PENDING, SAVE_STATUS_SAVING}
        # Conditional atomic update — only one caller wins.
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.id == save_request_id)
            .where(OfficeSaveRequest.edit_session_id == edit_session_id)
            .where(OfficeSaveRequest.status.in_(eligible))
            .values(
                status=SAVE_STATUS_CALLBACK_RECEIVED,
                error_code=None,
                error_message=None,
            )
        )
        result = session_db.execute(stmt)
        if result.rowcount == 0:
            return None
        session_db.expire_all()
        return OfficeSaveRequestRepository.get_by_id(session_db, save_request_id)

    @staticmethod
    def mark_saved(
        session_db: Session,
        save_request_id: uuid.UUID,
        *,
        completed_at: datetime,
    ) -> None:
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.id == save_request_id)
            .values(
                status=SAVE_STATUS_SAVED,
                completed_at=completed_at,
                error_code=None,
                error_message=None,
            )
        )
        session_db.execute(stmt)

    @staticmethod
    def mark_failed(
        session_db: Session,
        save_request_id: uuid.UUID,
        *,
        error_code: str,
        error_message: str | None = None,
        completed_at: datetime,
    ) -> None:
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.id == save_request_id)
            .values(
                status=SAVE_STATUS_FAILED,
                completed_at=completed_at,
                error_code=error_code,
                error_message=error_message,
            )
        )
        session_db.execute(stmt)

    @staticmethod
    def fail_active_by_edit_session(
        session_db: Session,
        edit_session_id: uuid.UUID,
        *,
        error_code: str,
        completed_at: datetime,
    ) -> int:
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.edit_session_id == edit_session_id)
            .where(OfficeSaveRequest.status.in_(ACTIVE_SAVE_STATUSES))
            .values(
                status=SAVE_STATUS_FAILED,
                completed_at=completed_at,
                error_code=error_code,
            )
        )
        result = session_db.execute(stmt)
        return result.rowcount

    @staticmethod
    def expire_old(session_db: Session, *, now: datetime) -> int:
        stmt = (
            update(OfficeSaveRequest)
            .where(OfficeSaveRequest.expires_at <= now)
            .values(status=SAVE_STATUS_FAILED, error_code="office_save_request_expired")
        )
        result = session_db.execute(stmt)
        return result.rowcount

    @staticmethod
    def recover_staged(session_db: Session) -> list[OfficeSaveRequest]:
        """Return save_requests stuck in STAGED or legacy COMMITTING with a marker."""
        stmt = (
            select(OfficeSaveRequest)
            .where(
                OfficeSaveRequest.status.in_(
                    {SAVE_STATUS_STAGED, SAVE_STATUS_COMMITTING}
                )
            )
            .where(OfficeSaveRequest.staged_object_key.is_not(None))
        )
        return list(session_db.scalars(stmt).all())
