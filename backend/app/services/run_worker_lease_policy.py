"""Run worker ownership and lease precondition policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException


class RunWorkerLeasePolicy:
    """Validate worker identity, claim ownership, and lease freshness."""

    @staticmethod
    def normalize_worker_id(worker_id: str) -> str:
        normalized = worker_id.strip()
        if not normalized:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="worker_id cannot be empty",
            )
        return normalized

    @staticmethod
    def normalize_lease_seconds(lease_seconds: int) -> int:
        if lease_seconds <= 0:
            return 30
        return lease_seconds

    @staticmethod
    def ensure_worker_owns_run(db_run: Any, worker_id: str) -> None:
        claimed_by = getattr(db_run, "claimed_by", None)
        if not claimed_by:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Run is not claimed by a worker",
            )
        if claimed_by != worker_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Run is claimed by another worker",
            )

    @staticmethod
    def ensure_active_claim(db_run: Any) -> None:
        lease_expires_at = getattr(db_run, "lease_expires_at", None)
        if lease_expires_at is None:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Run claim is missing a lease",
            )
        if lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
        if lease_expires_at <= datetime.now(timezone.utc):
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Run claim has expired",
            )
