from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.run_transition_policy import (
    RUN_TRANSITION_APPLY,
    RUN_TRANSITION_NOOP,
    RunTransitionPolicy,
)


def _run(
    *,
    status: str,
    claimed_by: str | None = "worker-1",
    lease_expires_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        claimed_by=claimed_by,
        lease_expires_at=lease_expires_at
        or datetime.now(timezone.utc) + timedelta(minutes=5),
    )


def test_start_transition_allows_claimed_run_with_active_lease() -> None:
    decision = RunTransitionPolicy.evaluate_start(_run(status="claimed"), "worker-1")

    assert decision == RUN_TRANSITION_APPLY


def test_start_transition_noops_terminal_run() -> None:
    decision = RunTransitionPolicy.evaluate_start(_run(status="completed"), "worker-1")

    assert decision == RUN_TRANSITION_NOOP


def test_start_transition_rejects_unclaimed_queued_run() -> None:
    with pytest.raises(AppException) as exc_info:
        RunTransitionPolicy.evaluate_start(_run(status="queued"), "worker-1")

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST


def test_fail_transition_allows_running_run_for_owner() -> None:
    decision = RunTransitionPolicy.evaluate_fail(_run(status="running"), "worker-1")

    assert decision == RUN_TRANSITION_APPLY


def test_fail_transition_noops_terminal_run() -> None:
    decision = RunTransitionPolicy.evaluate_fail(_run(status="failed"), "worker-1")

    assert decision == RUN_TRANSITION_NOOP


def test_fail_transition_rejects_queued_run() -> None:
    with pytest.raises(AppException) as exc_info:
        RunTransitionPolicy.evaluate_fail(_run(status="queued"), "worker-1")

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST
