from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.run import RunStatus
from app.services.run_transition_policy import (
    RUN_TRANSITION_APPLY,
    RUN_TRANSITION_NOOP,
    RunTransitionPolicy,
)

DEFAULT_NOW = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)


def _run(
    *,
    status: RunStatus,
    claimed_by: str | None = "worker-1",
    lease_expires_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        claimed_by=claimed_by,
        lease_expires_at=lease_expires_at or DEFAULT_NOW + timedelta(minutes=5),
    )


def test_start_transition_allows_claimed_run_with_active_lease() -> None:
    decision = RunTransitionPolicy.evaluate_start(
        _run(status=RunStatus.CLAIMED),
        "worker-1",
        now=DEFAULT_NOW,
    )

    assert decision == RUN_TRANSITION_APPLY


def test_start_transition_noops_terminal_run() -> None:
    decision = RunTransitionPolicy.evaluate_start(
        _run(status=RunStatus.COMPLETED),
        "worker-1",
        now=DEFAULT_NOW,
    )

    assert decision == RUN_TRANSITION_NOOP


def test_start_transition_rejects_unclaimed_queued_run() -> None:
    with pytest.raises(AppException) as exc_info:
        RunTransitionPolicy.evaluate_start(
            _run(status=RunStatus.QUEUED),
            "worker-1",
            now=DEFAULT_NOW,
        )

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST


def test_start_transition_uses_supplied_now_for_claim_freshness() -> None:
    now = datetime(2000, 1, 1, tzinfo=timezone.utc)
    decision = RunTransitionPolicy.evaluate_start(
        _run(status=RunStatus.CLAIMED, lease_expires_at=now + timedelta(minutes=1)),
        "worker-1",
        now=now,
    )

    assert decision == RUN_TRANSITION_APPLY


def test_fail_transition_allows_running_run_for_owner() -> None:
    decision = RunTransitionPolicy.evaluate_fail(
        _run(status=RunStatus.RUNNING),
        "worker-1",
        now=DEFAULT_NOW,
    )

    assert decision == RUN_TRANSITION_APPLY


def test_fail_transition_noops_terminal_run() -> None:
    decision = RunTransitionPolicy.evaluate_fail(
        _run(status=RunStatus.FAILED),
        "worker-1",
        now=DEFAULT_NOW,
    )

    assert decision == RUN_TRANSITION_NOOP


def test_fail_transition_rejects_queued_run() -> None:
    with pytest.raises(AppException) as exc_info:
        RunTransitionPolicy.evaluate_fail(
            _run(status=RunStatus.QUEUED),
            "worker-1",
            now=DEFAULT_NOW,
        )

    assert exc_info.value.error_code is ErrorCode.BAD_REQUEST


def test_fail_transition_uses_supplied_now_for_claim_freshness() -> None:
    now = datetime(2000, 1, 1, tzinfo=timezone.utc)
    decision = RunTransitionPolicy.evaluate_fail(
        _run(status=RunStatus.CLAIMED, lease_expires_at=now + timedelta(minutes=1)),
        "worker-1",
        now=now,
    )

    assert decision == RUN_TRANSITION_APPLY
