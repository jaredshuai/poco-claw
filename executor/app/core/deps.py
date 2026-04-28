import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException

TASK_LEASE_EXPIRES_AT_HEADER = "X-Poco-Task-Lease-Expires-At"
TASK_LEASE_SIGNATURE_HEADER = "X-Poco-Task-Lease-Signature"


def _expected_executor_token() -> str:
    return (os.getenv("CALLBACK_TOKEN") or "").strip()


def require_executor_token(
    authorization: str | None = Header(default=None),
) -> None:
    """Validate manager-to-executor task execution requests."""
    scheme, _, token = (authorization or "").partition(" ")
    expected_token = _expected_executor_token()
    if (
        scheme.lower() != "bearer"
        or not token
        or not expected_token
        or not hmac.compare_digest(token.strip(), expected_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid executor token")


def _task_lease_signature(
    *,
    callback_token: str,
    session_id: str,
    run_id: str | None,
    expires_at: int,
) -> str:
    payload = f"{session_id}\n{run_id or ''}\n{expires_at}".encode()
    return hmac.new(
        callback_token.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


def require_executor_task_lease(
    *,
    session_id: str,
    run_id: str | None,
    expires_at_header: str | None,
    signature_header: str | None,
) -> None:
    """Validate the short-lived task lease bound to this execution request."""
    expected_token = _expected_executor_token()
    if not expected_token or not expires_at_header or not signature_header:
        raise HTTPException(status_code=403, detail="Invalid executor task lease")

    try:
        expires_at = int(expires_at_header)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail="Invalid executor task lease",
        ) from exc

    if expires_at <= int(time.time()):
        raise HTTPException(status_code=403, detail="Executor task lease expired")

    expected_signature = _task_lease_signature(
        callback_token=expected_token,
        session_id=session_id,
        run_id=run_id,
        expires_at=expires_at,
    )
    if not hmac.compare_digest(signature_header.strip(), expected_signature):
        raise HTTPException(status_code=403, detail="Invalid executor task lease")
