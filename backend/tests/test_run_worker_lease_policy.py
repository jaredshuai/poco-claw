from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.run_worker_lease_policy import RunWorkerLeasePolicy


def test_normalize_worker_id_rejects_empty_value() -> None:
    with pytest.raises(AppException) as exc_info:
        RunWorkerLeasePolicy.normalize_worker_id("   ")

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST


def test_normalize_lease_seconds_keeps_positive_value() -> None:
    assert RunWorkerLeasePolicy.normalize_lease_seconds(60) == 60


def test_normalize_lease_seconds_defaults_non_positive_values() -> None:
    assert RunWorkerLeasePolicy.normalize_lease_seconds(0) == 30
    assert RunWorkerLeasePolicy.normalize_lease_seconds(-5) == 30


def test_ensure_worker_owns_run_rejects_unclaimed_run() -> None:
    db_run = SimpleNamespace(claimed_by=None)

    with pytest.raises(AppException) as exc_info:
        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, "worker-1")

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_ensure_worker_owns_run_rejects_other_worker() -> None:
    db_run = SimpleNamespace(claimed_by="worker-2")

    with pytest.raises(AppException) as exc_info:
        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, "worker-1")

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN


def test_ensure_active_claim_accepts_future_lease() -> None:
    db_run = SimpleNamespace(
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )

    RunWorkerLeasePolicy.ensure_active_claim(db_run)


def test_ensure_active_claim_rejects_expired_naive_lease() -> None:
    db_run = SimpleNamespace(
        lease_expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(minutes=5)
    )

    with pytest.raises(AppException) as exc_info:
        RunWorkerLeasePolicy.ensure_active_claim(db_run)

    assert exc_info.value.error_code is ErrorCode.FORBIDDEN
