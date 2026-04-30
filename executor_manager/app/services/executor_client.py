import hashlib
import hmac
from collections.abc import Callable

import httpx

from app.core.settings import get_settings
from app.core.observability.request_context import (
    generate_request_id,
    generate_trace_id,
    get_request_id,
    get_trace_id,
)
from app.services.clock import Clock, SystemClock

TASK_LEASE_TTL_SECONDS = 300
TASK_LEASE_EXPIRES_AT_HEADER = "X-Poco-Task-Lease-Expires-At"
TASK_LEASE_SIGNATURE_HEADER = "X-Poco-Task-Lease-Signature"


def build_executor_task_client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


class ExecutorClient:
    """Client for calling the Executor service."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        task_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.settings = get_settings()
        self.clock = clock or SystemClock()
        self.task_client_factory = task_client_factory or build_executor_task_client

    @staticmethod
    def _trace_headers() -> dict[str, str]:
        return {
            "X-Request-ID": get_request_id() or generate_request_id(),
            "X-Trace-ID": get_trace_id() or generate_trace_id(),
        }

    @staticmethod
    def _task_lease_signature(
        *,
        task_lease_secret: str,
        session_id: str,
        run_id: str | None,
        expires_at: int,
    ) -> str:
        payload = f"{session_id}\n{run_id or ''}\n{expires_at}".encode()
        return hmac.new(
            task_lease_secret.strip().encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

    def _now_epoch_seconds(self) -> int:
        return int(self.clock.now_utc().timestamp())

    def _execution_headers(
        self,
        *,
        callback_token: str,
        task_lease_secret: str,
        session_id: str,
        run_id: str | None,
    ) -> dict[str, str]:
        expires_at = self._now_epoch_seconds() + TASK_LEASE_TTL_SECONDS
        return {
            **self._trace_headers(),
            "Authorization": f"Bearer {callback_token}",
            TASK_LEASE_EXPIRES_AT_HEADER: str(expires_at),
            TASK_LEASE_SIGNATURE_HEADER: self._task_lease_signature(
                task_lease_secret=task_lease_secret,
                session_id=session_id,
                run_id=run_id,
                expires_at=expires_at,
            ),
        }

    async def execute_task(
        self,
        executor_url: str,
        session_id: str,
        run_id: str | None,
        prompt: str,
        callback_url: str,
        callback_token: str,
        config: dict,
        task_lease_secret: str | None = None,
        callback_base_url: str | None = None,
        sdk_session_id: str | None = None,
        permission_mode: str = "default",
    ) -> str:
        """Call Executor to execute a task.

        Args:
            executor_url: Executor service URL
            session_id: Session ID
            prompt: Task prompt
            callback_url: Callback URL
            callback_token: Callback token
            task_lease_secret: Secret used to sign the short-lived task lease
            config: Task configuration
            callback_base_url: Base URL for callback-related APIs
            sdk_session_id: Claude SDK session ID for resuming conversations
        """
        resolved_task_lease_secret = (task_lease_secret or callback_token).strip()
        async with self.task_client_factory() as client:
            response = await client.post(
                f"{executor_url}/v1/tasks/execute",
                json={
                    "session_id": session_id,
                    "run_id": run_id,
                    "prompt": prompt,
                    "callback_url": callback_url,
                    "callback_token": callback_token,
                    "callback_base_url": callback_base_url,
                    "config": config,
                    "sdk_session_id": sdk_session_id,
                    "permission_mode": permission_mode or "default",
                },
                headers=self._execution_headers(
                    callback_token=callback_token,
                    task_lease_secret=resolved_task_lease_secret,
                    session_id=session_id,
                    run_id=run_id,
                ),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            response.raise_for_status()
            data = response.json()
            return data["session_id"]
