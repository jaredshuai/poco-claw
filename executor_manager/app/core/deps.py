import hmac

from fastapi import Header, HTTPException

from app.core.settings import get_settings


def require_callback_token(
    authorization: str | None = Header(default=None),
) -> None:
    """Validate the callback token sent by executor-side helper scripts."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    settings = get_settings()
    expected_token = (settings.callback_token or "").strip()
    if (
        not token
        or not expected_token
        or not hmac.compare_digest(token, expected_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid callback token")


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Validate the X-Internal-Token header for control-plane endpoints.

    Protects mutating control-plane routes (task create, executor cancel/delete,
    executor load) from anonymous callers, mirroring backend's
    require_internal_token. An unset configured token is treated as a
    safe-by-default refusal rather than an open endpoint.
    """
    token = (x_internal_token or "").strip()
    settings = get_settings()
    expected_token = (settings.internal_api_token or "").strip()
    if (
        not expected_token
        or not token
        or not hmac.compare_digest(token, expected_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid internal token")
