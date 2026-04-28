import hmac
import uuid
from typing import Annotated, Generator

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.settings import get_settings
from app.repositories.session_repository import SessionRepository

DEFAULT_USER_ID = "default"


def _token_matches(provided: str | None, expected: str) -> bool:
    provided_token = (provided or "").strip()
    expected_token = expected.strip()
    return bool(
        provided_token
        and expected_token
        and hmac.compare_digest(provided_token, expected_token)
    )


def get_current_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    x_user_id_token: Annotated[str | None, Header(alias="X-User-Id-Token")] = None,
) -> str:
    """FastAPI dependency for the current user id.

    Auth is expected to be enforced by a trusted edge/proxy or by internal
    callers. The single-user DEFAULT_USER_ID fallback is available only when
    ALLOW_DEFAULT_USER is explicitly enabled.
    """
    settings = get_settings()
    value = (x_user_id or "").strip()
    if not value:
        if getattr(settings, "allow_default_user", False):
            return DEFAULT_USER_ID
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="User identity is required",
        )

    trusted_user_header_token = (
        getattr(settings, "trusted_user_header_token", "") or ""
    ).strip()
    if _token_matches(x_user_id_token, trusted_user_header_token):
        return value

    internal_api_token = (settings.internal_api_token or "").strip()
    if _token_matches(x_internal_token, internal_api_token):
        return value

    raise AppException(
        error_code=ErrorCode.FORBIDDEN,
        message="X-User-Id header is not trusted",
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Validate X-Internal-Token header for internal API endpoints."""
    settings = get_settings()
    internal_api_token = (settings.internal_api_token or "").strip()
    if not internal_api_token:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Internal API token is not configured",
        )
    if not _token_matches(x_internal_token, internal_api_token):
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Invalid internal token",
        )


def get_user_id_by_session_id(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> str:
    """Resolve user id by session id for internal APIs."""
    db_session = SessionRepository.get_by_id(db, session_id)
    if not db_session:
        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message=f"Session not found: {session_id}",
        )
    return db_session.user_id
