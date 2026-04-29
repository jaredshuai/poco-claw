"""Short-lived state and command helpers for OnlyOffice editing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
import secrets
import uuid

import httpx
import jwt

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.settings import get_settings
from app.services.clock import Clock, SystemClock


logger = logging.getLogger(__name__)

SAVE_STATUS_PENDING = "pending"
SAVE_STATUS_SAVING = "saving"
SAVE_STATUS_COMMITTING = "committing"
SAVE_STATUS_SAVED = "saved"
SAVE_STATUS_FAILED = "failed"
ACTIVE_SAVE_STATUSES = {
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_COMMITTING,
}


@dataclass
class OfficeEditSession:
    edit_session_id: str
    session_id: str
    user_id: str
    file_path: str
    object_key: str
    mime_type: str | None
    manifest_key: str | None
    document_key: str
    callback_token: str
    expires_at: datetime
    discarded: bool = False


@dataclass
class OfficeSaveRequest:
    save_request_id: str
    edit_session_id: str
    session_id: str
    user_id: str
    file_path: str
    document_key: str
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class OfficeEditingStore:
    """Short-lived edit/save state with optional file-backed recovery."""

    def __init__(
        self,
        *,
        state_path: str | Path | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._edit_sessions: dict[str, OfficeEditSession] = {}
        self._tokens: dict[str, str] = {}
        self._save_requests: dict[str, OfficeSaveRequest] = {}
        self._state_path = Path(state_path) if state_path else None
        self._clock = clock or SystemClock()
        self._load_state()

    def _now(self) -> datetime:
        return self._clock.now_utc().astimezone(UTC)

    def create_edit_session(
        self,
        *,
        session_id: str,
        user_id: str,
        file_path: str,
        object_key: str,
        mime_type: str | None,
        manifest_key: str | None,
        document_key: str,
        edit_session_id: str | None = None,
    ) -> OfficeEditSession:
        now = self._now()
        settings = get_settings()
        resolved_edit_session_id = edit_session_id or str(uuid.uuid4())
        existing = self._edit_sessions.get(resolved_edit_session_id)
        if existing is not None:
            self._tokens.pop(existing.callback_token, None)
        session = OfficeEditSession(
            edit_session_id=resolved_edit_session_id,
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
        )
        self._edit_sessions[session.edit_session_id] = session
        self._tokens[session.callback_token] = session.edit_session_id
        self._persist_state()
        return session

    def get_edit_session(self, edit_session_id: str) -> OfficeEditSession | None:
        self.cleanup_expired()
        session = self._edit_sessions.get(edit_session_id)
        if not session or session.discarded:
            return None
        return session

    def discard_edit_session(self, edit_session_id: str) -> bool:
        session = self._edit_sessions.get(edit_session_id)
        if not session or session.discarded:
            return False
        session.discarded = True
        self._tokens.pop(session.callback_token, None)
        self._persist_state()
        return True

    def update_edit_session_object_key(
        self,
        edit_session_id: str,
        object_key: str,
    ) -> bool:
        session = self._edit_sessions.get(edit_session_id)
        if not session or session.discarded:
            return False
        session.object_key = object_key
        self._persist_state()
        return True

    def complete_save_request(
        self,
        save_request_id: str,
        *,
        edit_session_id: str,
        object_key: str | None = None,
    ) -> None:
        """Mark a save request saved and update the edit session in one state write."""
        save_request = self._save_requests.get(save_request_id)
        if not save_request:
            return

        session = self._edit_sessions.get(edit_session_id)
        previous_session_object_key = session.object_key if session else None
        previous_save_state = (
            save_request.status,
            save_request.updated_at,
            save_request.completed_at,
            save_request.error_code,
            save_request.error_message,
        )

        now = self._now()
        try:
            if object_key and session and not session.discarded:
                session.object_key = object_key
            save_request.status = SAVE_STATUS_SAVED
            save_request.updated_at = now
            save_request.completed_at = now
            save_request.error_code = None
            save_request.error_message = None
            self._persist_state()
        except Exception:
            if session and previous_session_object_key is not None:
                session.object_key = previous_session_object_key
            (
                save_request.status,
                save_request.updated_at,
                save_request.completed_at,
                save_request.error_code,
                save_request.error_message,
            ) = previous_save_state
            raise

    def resolve_by_token(self, token: str) -> OfficeEditSession | None:
        edit_session_id = self._tokens.get(token)
        if not edit_session_id:
            return None
        return self.get_edit_session(edit_session_id)

    def create_save_request(self, session: OfficeEditSession) -> OfficeSaveRequest:
        now = self._now()
        settings = get_settings()
        save_request = OfficeSaveRequest(
            save_request_id=str(uuid.uuid4()),
            edit_session_id=session.edit_session_id,
            session_id=session.session_id,
            user_id=session.user_id,
            file_path=session.file_path,
            document_key=session.document_key,
            status=SAVE_STATUS_PENDING,
            created_at=now,
            updated_at=now,
            expires_at=now
            + timedelta(seconds=settings.office_save_request_ttl_seconds),
        )
        self._save_requests[save_request.save_request_id] = save_request
        self._persist_state()
        return save_request

    def get_active_save_request(self, edit_session_id: str) -> OfficeSaveRequest | None:
        self.cleanup_expired()
        for save_request in self._save_requests.values():
            if (
                save_request.edit_session_id == edit_session_id
                and save_request.status in ACTIVE_SAVE_STATUSES
            ):
                return save_request
        return None

    def get_save_request(self, save_request_id: str) -> OfficeSaveRequest | None:
        self.cleanup_expired()
        return self._save_requests.get(save_request_id)

    def cleanup_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        """Remove expired edit sessions and stale save request records."""
        now = now or self._now()
        expired_session_ids = [
            edit_session_id
            for edit_session_id, session in self._edit_sessions.items()
            if session.discarded or session.expires_at <= now
        ]

        for edit_session_id in expired_session_ids:
            session = self._edit_sessions.pop(edit_session_id)
            self._tokens.pop(session.callback_token, None)
            for save_request in self._save_requests.values():
                if (
                    save_request.edit_session_id == edit_session_id
                    and save_request.status in ACTIVE_SAVE_STATUSES
                ):
                    self._mark(
                        save_request.save_request_id,
                        SAVE_STATUS_FAILED,
                        completed=True,
                        error_code="office_edit_session_expired",
                    )

        expired_save_request_ids = [
            save_request_id
            for save_request_id, save_request in self._save_requests.items()
            if save_request.expires_at <= now
        ]
        for save_request_id in expired_save_request_ids:
            self._save_requests.pop(save_request_id, None)

        if expired_session_ids or expired_save_request_ids:
            self._persist_state()

        return {
            "edit_sessions": len(expired_session_ids),
            "save_requests": len(expired_save_request_ids),
        }

    def mark_saving(self, save_request_id: str) -> None:
        self._mark(save_request_id, SAVE_STATUS_SAVING)

    def try_begin_commit(
        self,
        save_request_id: str,
        *,
        edit_session_id: str,
    ) -> OfficeSaveRequest | None:
        """Claim save writeback commit ownership for one callback handler."""
        self.cleanup_expired()
        save_request = self._save_requests.get(save_request_id)
        if (
            save_request is None
            or save_request.edit_session_id != edit_session_id
            or save_request.status not in {SAVE_STATUS_PENDING, SAVE_STATUS_SAVING}
        ):
            return None

        previous_save_state = (
            save_request.status,
            save_request.updated_at,
            save_request.completed_at,
            save_request.error_code,
            save_request.error_message,
        )
        now = self._now()
        try:
            save_request.status = SAVE_STATUS_COMMITTING
            save_request.updated_at = now
            save_request.error_code = None
            save_request.error_message = None
            self._persist_state()
        except Exception:
            (
                save_request.status,
                save_request.updated_at,
                save_request.completed_at,
                save_request.error_code,
                save_request.error_message,
            ) = previous_save_state
            raise
        return save_request

    def mark_saved(self, save_request_id: str) -> None:
        self._mark(save_request_id, SAVE_STATUS_SAVED, completed=True)

    def mark_failed(
        self,
        save_request_id: str,
        *,
        error_code: str,
        error_message: str | None = None,
    ) -> None:
        self._mark(
            save_request_id,
            SAVE_STATUS_FAILED,
            completed=True,
            error_code=error_code,
            error_message=error_message,
        )

    def _mark(
        self,
        save_request_id: str,
        status: str,
        *,
        completed: bool = False,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        save_request = self._save_requests.get(save_request_id)
        if not save_request:
            return
        now = self._now()
        save_request.status = status
        save_request.updated_at = now
        save_request.error_code = error_code
        save_request.error_message = error_message
        if completed:
            save_request.completed_at = now
        self._persist_state()

    def _persist_state(self) -> None:
        if self._state_path is None:
            return

        payload = {
            "version": 1,
            "edit_sessions": [
                self._serialize_edit_session(session)
                for session in self._edit_sessions.values()
            ],
            "save_requests": [
                self._serialize_save_request(save_request)
                for save_request in self._save_requests.values()
            ],
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._state_path.with_name(f"{self._state_path.name}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temp_path.replace(self._state_path)

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to load Office editing state file", exc_info=True)
            return

        edit_sessions = payload.get("edit_sessions", [])
        if isinstance(edit_sessions, list):
            for raw_session in edit_sessions:
                if not isinstance(raw_session, dict):
                    continue
                session = self._deserialize_edit_session(raw_session)
                if session is None:
                    continue
                self._edit_sessions[session.edit_session_id] = session
                if not session.discarded:
                    self._tokens[session.callback_token] = session.edit_session_id

        save_requests = payload.get("save_requests", [])
        if isinstance(save_requests, list):
            for raw_save_request in save_requests:
                if not isinstance(raw_save_request, dict):
                    continue
                save_request = self._deserialize_save_request(raw_save_request)
                if save_request is None:
                    continue
                self._save_requests[save_request.save_request_id] = save_request

        self.cleanup_expired()

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _deserialize_datetime(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @classmethod
    def _serialize_edit_session(cls, session: OfficeEditSession) -> dict[str, object]:
        return {
            "edit_session_id": session.edit_session_id,
            "session_id": session.session_id,
            "user_id": session.user_id,
            "file_path": session.file_path,
            "object_key": session.object_key,
            "mime_type": session.mime_type,
            "manifest_key": session.manifest_key,
            "document_key": session.document_key,
            "callback_token": session.callback_token,
            "expires_at": cls._serialize_datetime(session.expires_at),
            "discarded": session.discarded,
        }

    @classmethod
    def _deserialize_edit_session(
        cls, raw_session: dict[str, object]
    ) -> OfficeEditSession | None:
        expires_at = cls._deserialize_datetime(raw_session.get("expires_at"))
        required = [
            "edit_session_id",
            "session_id",
            "user_id",
            "file_path",
            "object_key",
            "document_key",
            "callback_token",
        ]
        if expires_at is None or not all(
            isinstance(raw_session.get(field), str) for field in required
        ):
            return None
        mime_type = raw_session.get("mime_type")
        manifest_key = raw_session.get("manifest_key")
        return OfficeEditSession(
            edit_session_id=str(raw_session["edit_session_id"]),
            session_id=str(raw_session["session_id"]),
            user_id=str(raw_session["user_id"]),
            file_path=str(raw_session["file_path"]),
            object_key=str(raw_session["object_key"]),
            mime_type=mime_type if isinstance(mime_type, str) else None,
            manifest_key=manifest_key if isinstance(manifest_key, str) else None,
            document_key=str(raw_session["document_key"]),
            callback_token=str(raw_session["callback_token"]),
            expires_at=expires_at,
            discarded=bool(raw_session.get("discarded", False)),
        )

    @classmethod
    def _serialize_save_request(
        cls, save_request: OfficeSaveRequest
    ) -> dict[str, object]:
        return {
            "save_request_id": save_request.save_request_id,
            "edit_session_id": save_request.edit_session_id,
            "session_id": save_request.session_id,
            "user_id": save_request.user_id,
            "file_path": save_request.file_path,
            "document_key": save_request.document_key,
            "status": save_request.status,
            "created_at": cls._serialize_datetime(save_request.created_at),
            "updated_at": cls._serialize_datetime(save_request.updated_at),
            "expires_at": cls._serialize_datetime(save_request.expires_at),
            "completed_at": cls._serialize_datetime(save_request.completed_at),
            "error_code": save_request.error_code,
            "error_message": save_request.error_message,
        }

    @classmethod
    def _deserialize_save_request(
        cls, raw_save_request: dict[str, object]
    ) -> OfficeSaveRequest | None:
        created_at = cls._deserialize_datetime(raw_save_request.get("created_at"))
        updated_at = cls._deserialize_datetime(raw_save_request.get("updated_at"))
        expires_at = cls._deserialize_datetime(raw_save_request.get("expires_at"))
        completed_at = cls._deserialize_datetime(raw_save_request.get("completed_at"))
        required = [
            "save_request_id",
            "edit_session_id",
            "session_id",
            "user_id",
            "file_path",
            "document_key",
            "status",
        ]
        if (
            created_at is None
            or updated_at is None
            or expires_at is None
            or not all(
                isinstance(raw_save_request.get(field), str) for field in required
            )
        ):
            return None
        error_code = raw_save_request.get("error_code")
        error_message = raw_save_request.get("error_message")
        return OfficeSaveRequest(
            save_request_id=str(raw_save_request["save_request_id"]),
            edit_session_id=str(raw_save_request["edit_session_id"]),
            session_id=str(raw_save_request["session_id"]),
            user_id=str(raw_save_request["user_id"]),
            file_path=str(raw_save_request["file_path"]),
            document_key=str(raw_save_request["document_key"]),
            status=str(raw_save_request["status"]),
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
            completed_at=completed_at,
            error_code=error_code if isinstance(error_code, str) else None,
            error_message=error_message if isinstance(error_message, str) else None,
        )


def _get_state_path_from_settings() -> str | None:
    state_path = get_settings().office_editing_state_file.strip()
    return state_path or None


office_editing_store = OfficeEditingStore(state_path=_get_state_path_from_settings())


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
    while True:
        stats = store.cleanup_expired()
        if stats.get("edit_sessions", 0) or stats.get("save_requests", 0):
            logger.info(
                "Office editing cleanup completed: edit_sessions=%s, save_requests=%s",
                stats.get("edit_sessions", 0),
                stats.get("save_requests", 0),
            )
        await asyncio.sleep(interval_seconds)
