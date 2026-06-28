"""Run lifecycle transition precondition policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.run import RunStatus
from app.services.run_worker_lease_policy import RunWorkerLeasePolicy

RUN_TRANSITION_APPLY = "apply"
RUN_TRANSITION_NOOP = "noop"
RunTransitionDecision = Literal["apply", "noop"]

TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}
)


class RunTransitionPolicy:
    """Evaluate run status transitions without touching persistence."""

    @staticmethod
    def evaluate_start(
        db_run: Any,
        worker_id: str,
        *,
        now: datetime,
    ) -> RunTransitionDecision:
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status == RunStatus.RUNNING:
            RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
            return RUN_TRANSITION_NOOP

        if db_run.status != RunStatus.CLAIMED:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be started: {db_run.status}",
            )

        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
        RunWorkerLeasePolicy.ensure_active_claim(db_run, now=now)
        return RUN_TRANSITION_APPLY

    @staticmethod
    def evaluate_fail(
        db_run: Any,
        worker_id: str,
        *,
        now: datetime,
    ) -> RunTransitionDecision:
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status not in [RunStatus.CLAIMED, RunStatus.RUNNING]:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be failed: {db_run.status}",
            )

        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
        if db_run.status == RunStatus.CLAIMED:
            RunWorkerLeasePolicy.ensure_active_claim(db_run, now=now)
        return RUN_TRANSITION_APPLY

    @staticmethod
    def evaluate_complete(
        db_run: Any,
        worker_id: str,
        *,
        now: datetime,
    ) -> RunTransitionDecision:
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status != RunStatus.RUNNING:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be completed: {db_run.status}",
            )

        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
        return RUN_TRANSITION_APPLY

    @staticmethod
    def evaluate_cancel(
        db_run: Any,
        worker_id: str,
        *,
        now: datetime,
    ) -> RunTransitionDecision:
        """Worker-initiated cancel: a worker may only cancel a run it owns.

        Requires worker ownership for claimed/running runs (queued runs have no
        owner). No lease-freshness check — canceling an expired-but-owned claim
        is allowed. Used by future worker-side cancel use cases; today no
        production path calls this.
        """
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status not in [
            RunStatus.QUEUED,
            RunStatus.CLAIMED,
            RunStatus.RUNNING,
        ]:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be canceled: {db_run.status}",
            )

        # queued runs have no claimed_by, so skip worker ownership check
        if db_run.status in (RunStatus.CLAIMED, RunStatus.RUNNING):
            RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
        return RUN_TRANSITION_APPLY

    @staticmethod
    def evaluate_cancel_by_owner(
        db_run: Any,
        *,
        now: datetime,
    ) -> RunTransitionDecision:
        """Session-owner-initiated cancel: the owner may cancel any of their
        session's runs regardless of which worker claimed it.

        Unlike :meth:`evaluate_cancel`, this performs only status-precondition
        validation (terminal -> noop, queued/claimed/running -> apply, anything
        else -> bad request) and intentionally skips worker ownership: a session
        owner has authority over all runs in their session. This is the cancel
        semantics used by the user-facing ``cancel_session`` path, which must go
        through the state machine rather than mutating status directly.
        """
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status not in [
            RunStatus.QUEUED,
            RunStatus.CLAIMED,
            RunStatus.RUNNING,
        ]:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be canceled: {db_run.status}",
            )
        return RUN_TRANSITION_APPLY
