"""Short-lived state and command helpers for OnlyOffice editing.

State is persisted in PostgreSQL (``office_edit_sessions`` and
``office_save_requests`` tables) so it survives process restarts. Each store
method takes a SQLAlchemy ``Session`` so writes are transactional with the
caller's request scope.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
import secrets

import httpx
import jwt

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.settings import get_settings
from app.repositories.office_edit_session_repository import OfficeEditSessionRepository
from app.repositories.office_save_request_repository import (
    OfficeSaveRequestRepository,
)
from app.services.clock import Clock, SystemClock
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

logger = logging.getLogger(__name__)


class OfficeEditingStore:
    """DB-backed edit/save state for OnlyOffice sessions.

    Every mutating method takes a ``db: Session`` first so writes join the
    caller's transaction. State is read back from the database rather than held
    in memory, so it survives restarts.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def _now(self) -> datetime:
        return self._clock.now_utc().astimezone(UTC)

    # ------------------------------------------------------------------ #
    # Edit sessions
    # ------------------------------------------------------------------ #

    def create_edit_session(
        self,
        db,
        *,
        session_id: str,
        user_id: str,
        file_path: str,
        object_key: str,
        mime_type: str | None,
        manifest_key: str | None,
        document_key: str,
        edit_session_id=None,
    ):
        now = self._now()
        settings = get_settings()
        session = OfficeEditSessionRepository.create(
            db,
            session_id=session_id,
            user_id=user_id,
            file_path=file_path,
            object_key=object_key,
            mime_type=mime_type,
            manifest_key=manifest_key,
            document_key=document_key,
            callback_token=secrets.token_urlsafe(32),
            expires_at=now
            + timedelta(seconds=settings.office_edit_session_ttl_seconds),
            edit_session_id=edit_session_id,
        )
        db.flush()
        return session

    def get_edit_session(self, db, edit_session_id):
        session = OfficeEditSessionRepository.get_by_id(db, edit_session_id)
        if not session or session.discarded:
            return None
        return session

    def discard_edit_session(self, db, edit_session_id) -> bool:
        return OfficeEditSessionRepository.mark_discarded(db, edit_session_id)

    def update_edit_session_object_key(self, db, edit_session_id, object_key: str) -> bool:
        session = OfficeEditSessionRepository.get_by_id(db, edit_session_id)
        if not session or session.discarded:
            return False
        OfficeEditSessionRepository.update_object_key(db, edit_session_id, object_key)
        return True

    def resolve_by_token(self, db, token: str):
        return OfficeEditSessionRepository.get_by_callback_token(db, token)

    # ------------------------------------------------------------------ #
    # Save requests
    # ------------------------------------------------------------------ #

    def create_save_request(self, db, session):
        now = self._now()
        settings = get_settings()
        save_request = OfficeSaveRequestRepository.create(
            db,
            edit_session_id=session.edit_session_id,
            session_id=session.session_id,
            user_id=session.user_id,
            file_path=session.file_path,
            document_key=session.document_key,
            expires_at=now
            + timedelta(seconds=settings.office_save_request_ttl_seconds),
        )
        db.flush()
        return save_request

    def get_active_save_request(self, db, edit_session_id):
        return OfficeSaveRequestRepository.get_active_by_edit_session(
            db, edit_session_id
        )

    def get_save_request(self, db, save_request_id):
        return OfficeSaveRequestRepository.get_by_id(db, save_request_id)

    def mark_saving(self, db, save_request_id) -> None:
        OfficeSaveRequestRepository.mark_saving(db, save_request_id)

    def mark_staged(self, db, save_request_id, *, staged_object_key: str | None = None) -> None:
        sr = OfficeSaveRequestRepository.get_by_id(db, save_request_id)
        if sr is None:
            return
        if staged_object_key is None:
            staged_object_key = sr.staged_object_key or ""
        OfficeSaveRequestRepository.mark_staged(db, save_request_id, staged_object_key)

    def try_begin_commit(self, db, save_request_id, *, edit_session_id):
        """Atomically claim a save for writeback.

        Moves a pending/saving save_request to callback_received. Returns the
        updated row on success, None if another caller claimed it or it is no
        longer eligible.
        """
        return OfficeSaveRequestRepository.try_begin_commit(
            db, save_request_id, edit_session_id
        )

    def complete_save_request(
        self,
        db,
        save_request_id,
        *,
        edit_session_id,
        object_key: str | None = None,
    ) -> None:
        """Mark a save request saved and update the edit session atomically.

        Both writes run in the caller's transaction; if it rolls back the save
        request stays in its pre-completion state.
        """
        now = self._now()
        OfficeSaveRequestRepository.mark_saved(db, save_request_id, completed_at=now)
        if object_key:
            OfficeEditSessionRepository.update_object_key(
                db, edit_session_id, object_key
            )

    def mark_saved(self, db, save_request_id) -> None:
        OfficeSaveRequestRepository.mark_saved(
            db, save_request_id, completed_at=self._now()
        )

    def mark_failed(
        self,
        db,
        save_request_id,
        *,
        error_code: str,
        error_message: str | None = None,
    ) -> None:
        OfficeSaveRequestRepository.mark_failed(
            db,
            save_request_id,
            error_code=error_code,
            error_message=error_message,
            completed_at=self._now(),
        )

    # ------------------------------------------------------------------ #
    # Maintenance
    # ------------------------------------------------------------------ #

    def cleanup_expired(self, db, *, now: datetime | None = None) -> dict[str, int]:
        """Fail expired edit sessions + their active saves, then expire old saves."""
        now = now or self._now()
        expired_sessions = OfficeEditSessionRepository.expire_discarded_and_expired(
            db, now=now
        )
        expired_session_count = len(expired_sessions)
        failed_saves = 0
        for session in expired_sessions:
            failed_saves += OfficeSaveRequestRepository.fail_active_by_edit_session(
                db,
                session.id,
                error_code="office_edit_session_expired",
                completed_at=now,
            )
        expired_saves = OfficeSaveRequestRepository.expire_old(db, now=now)
        # Recover staged writebacks while we have the db open.
        self.recover_staged_writebacks(db)
        return {
            "edit_sessions": expired_session_count,
            "save_requests": failed_saves + expired_saves,
        }

    def recover_staged_writebacks(self, db) -> int:
        """Replay complete_save_request for save_requests stuck in STAGED/COMMITTING.

        After a crash between manifest flip and state commit, a save_request
        remains in STAGED (or legacy COMMITTING) with staged_object_key set.
        Retry completing the state so the caller sees SAVED.
        """
        stuck = OfficeSaveRequestRepository.recover_staged(db)
        recovered = 0
        for sr in stuck:
            logger.info(
                "recovering_staged_writeback",
                extra={
                    "save_request_id": sr.save_request_id,
                    "edit_session_id": sr.edit_session_id,
                    "session_id": sr.session_id,
                    "staged_object_key": sr.staged_object_key,
                },
            )
            try:
                self.complete_save_request(
                    db,
                    sr.save_request_id,
                    edit_session_id=sr.edit_session_id,
                    object_key=sr.staged_object_key,
                )
                recovered += 1
                logger.info(
                    "recovered_staged_writeback",
                    extra={"save_request_id": sr.save_request_id},
                )
            except Exception:
                logger.warning(
                    "recover_staged_writeback_failed",
                    extra={"save_request_id": sr.save_request_id},
                    exc_info=True,
                )
        return recovered


office_editing_store = OfficeEditingStore()


class OnlyOfficeCommandClient:
    """Client for the OnlyOffice Command Service."""

    async def forcesave(self, *, document_key: str, userdata: str) -> None:
        settings = get_settings()
        ds_url = settings.office_document_server_url.rstrip("/")
        if not ds_url:
            raise AppException(
                error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                message="OnlyOffice Document Server URL is not configured",
            )

        payload = {
            "c": "forcesave",
            "key": document_key,
            "userdata": userdata,
        }
        secret = settings.office_jwt_secret
        if secret:
            payload["token"] = jwt.encode(payload, secret, algorithm="HS256")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ds_url}/coauthoring/CommandService.ashx",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if int(data.get("error", 0)) != 0:
            raise AppException(
                error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                message="OnlyOffice forcesave command was rejected",
                details=data,
            )


async def run_office_editing_cleanup_loop(
    *,
    store: OfficeEditingStore,
    interval_seconds: float,
) -> None:
    """Periodically evict expired Office editing state."""
    from app.core.database import SessionLocal

    while True:
        try:
            db = SessionLocal()
            try:
                stats = store.cleanup_expired(db)
                db.commit()
            finally:
                db.close()
            if stats.get("edit_sessions", 0) or stats.get("save_requests", 0):
                logger.info(
                    "Office editing cleanup completed: edit_sessions=%s, save_requests=%s",
                    stats.get("edit_sessions", 0),
                    stats.get("save_requests", 0),
                )
        except Exception:
            logger.warning("Office editing cleanup loop iteration failed", exc_info=True)
        await asyncio.sleep(interval_seconds)
