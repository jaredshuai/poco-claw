"""Data access for office edit sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.office_edit_session import OfficeEditSession


class OfficeEditSessionRepository:
    """Data access layer for OnlyOffice edit sessions."""

    @staticmethod
    def create(
        session_db: Session,
        *,
        session_id: str,
        user_id: str,
        file_path: str,
        object_key: str,
        mime_type: str | None,
        manifest_key: str | None,
        document_key: str,
        callback_token: str,
        expires_at: datetime,
        edit_session_id: uuid.UUID | None = None,
    ) -> OfficeEditSession:
        edit_session = OfficeEditSession(
            session_id=session_id,
            user_id=user_id,
            file_path=file_path,
            object_key=object_key,
            mime_type=mime_type,
            manifest_key=manifest_key,
            document_key=document_key,
            callback_token=callback_token,
            expires_at=expires_at,
            discarded=False,
        )
        if edit_session_id is not None:
            edit_session.id = edit_session_id
        session_db.add(edit_session)
        return edit_session

    @staticmethod
    def get_by_id(
        session_db: Session, edit_session_id: uuid.UUID
    ) -> OfficeEditSession | None:
        return (
            session_db.query(OfficeEditSession)
            .filter(OfficeEditSession.id == edit_session_id)
            .first()
        )

    @staticmethod
    def get_by_callback_token(
        session_db: Session, token: str
    ) -> OfficeEditSession | None:
        return (
            session_db.query(OfficeEditSession)
            .filter(OfficeEditSession.callback_token == token)
            .filter(OfficeEditSession.discarded.is_(False))
            .first()
        )

    @staticmethod
    def mark_discarded(session_db: Session, edit_session_id: uuid.UUID) -> bool:
        """Soft-delete an edit session so its callback token stops resolving.

        Returns True when a row was affected.
        """
        stmt = (
            update(OfficeEditSession)
            .where(OfficeEditSession.id == edit_session_id)
            .where(OfficeEditSession.discarded.is_(False))
            .values(discarded=True)
        )
        result = session_db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    def update_object_key(
        session_db: Session,
        edit_session_id: uuid.UUID,
        object_key: str,
    ) -> None:
        stmt = (
            update(OfficeEditSession)
            .where(OfficeEditSession.id == edit_session_id)
            .values(object_key=object_key)
        )
        session_db.execute(stmt)

    @staticmethod
    def expire_discarded_and_expired(
        session_db: Session, *, now: datetime
    ) -> list[OfficeEditSession]:
        """Bulk-fail edit sessions that are discarded or past their TTL.

        Returns the affected rows so callers can cascade-save-request cleanup.
        """
        rows = (
            session_db.query(OfficeEditSession)
            .filter(
                OfficeEditSession.discarded.is_(True)
                | (OfficeEditSession.expires_at <= now)
            )
            .all()
        )
        return rows
