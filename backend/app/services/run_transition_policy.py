"""Run lifecycle transition precondition policy."""

from __future__ import annotations

from typing import Any, Literal

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.run_worker_lease_policy import RunWorkerLeasePolicy

RUN_TRANSITION_APPLY = "apply"
RUN_TRANSITION_NOOP = "noop"
RunTransitionDecision = Literal["apply", "noop"]

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled"})


class RunTransitionPolicy:
    """Evaluate run status transitions without touching persistence."""

    @staticmethod
    def evaluate_start(db_run: Any, worker_id: str) -> RunTransitionDecision:
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status == "running":
            RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
            return RUN_TRANSITION_NOOP

        if db_run.status != "claimed":
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be started: {db_run.status}",
            )

        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
        RunWorkerLeasePolicy.ensure_active_claim(db_run)
        return RUN_TRANSITION_APPLY

    @staticmethod
    def evaluate_fail(db_run: Any, worker_id: str) -> RunTransitionDecision:
        if db_run.status in TERMINAL_RUN_STATUSES:
            return RUN_TRANSITION_NOOP

        if db_run.status not in ["claimed", "running"]:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Run status cannot be failed: {db_run.status}",
            )

        RunWorkerLeasePolicy.ensure_worker_owns_run(db_run, worker_id)
        if db_run.status == "claimed":
            RunWorkerLeasePolicy.ensure_active_claim(db_run)
        return RUN_TRANSITION_APPLY
