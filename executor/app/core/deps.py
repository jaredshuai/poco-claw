import hmac
import os

from fastapi import Header, HTTPException


def require_executor_token(
    authorization: str | None = Header(default=None),
) -> None:
    """Validate manager-to-executor task execution requests."""
    scheme, _, token = (authorization or "").partition(" ")
    expected_token = (os.getenv("CALLBACK_TOKEN") or "").strip()
    if (
        scheme.lower() != "bearer"
        or not token
        or not expected_token
        or not hmac.compare_digest(token.strip(), expected_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid executor token")
