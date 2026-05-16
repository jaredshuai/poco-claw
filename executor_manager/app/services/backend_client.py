import asyncio
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from app.core.settings import get_settings
from app.core.observability.request_context import (
    generate_request_id,
    generate_trace_id,
    get_request_id,
    get_trace_id,
)


class BackendClientSettings(Protocol):
    backend_url: str
    internal_api_token: str


def build_backend_http_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
        timeout=httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0),
        trust_env=False,
    )


class BackendClient:
    """Client for communicating with the Backend service."""

    def __init__(
        self,
        *,
        settings: BackendClientSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
        http_client_factory: Callable[[str], httpx.AsyncClient] | None = None,
    ) -> None:
        self.settings = settings if settings is not None else get_settings()
        self.base_url = (self.settings.backend_url or "").rstrip("/")
        self._http_client = http_client
        self._http_client_factory = http_client_factory or build_backend_http_client

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = self._http_client_factory(self.base_url)
        return self._http_client

    @_client.setter
    def _client(self, value: httpx.AsyncClient) -> None:
        self._http_client = value

    @staticmethod
    def _trace_headers() -> dict[str, str]:
        # When called from an HTTP request handler, these come from middleware context.
        return {
            "X-Request-ID": get_request_id() or generate_request_id(),
            "X-Trace-ID": get_trace_id() or generate_trace_id(),
        }

    def _internal_headers(self) -> dict[str, str]:
        return {
            "X-Internal-Token": self.settings.internal_api_token,
            **self._trace_headers(),
        }

    def _internal_user_headers(self, user_id: str) -> dict[str, str]:
        return {
            **self._internal_headers(),
            "X-User-Id": user_id,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        retry_connect_errors: int = 0,
        **kwargs: Any,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, path, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if attempt >= retry_connect_errors:
                    raise
                attempt += 1
                await asyncio.sleep(min(0.25 * attempt, 1.0))

    async def create_session(self, user_id: str, config: dict) -> dict:
        """Create a session, returns session info dict with session_id and sdk_session_id."""
        response = await self._request(
            "POST",
            "/api/v1/sessions",
            json={"user_id": user_id, "config": config},
            headers=self._trace_headers(),
        )
        data = response.json()
        return data["data"]

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session details from the Backend service."""
        response = await self._request(
            "GET",
            f"/api/v1/sessions/{session_id}",
            headers=self._trace_headers(),
        )
        data = response.json()
        result = data.get("data", data)
        return result if isinstance(result, dict) else {}

    async def update_session_status(self, session_id: str, status: str) -> None:
        """Update session status."""
        await self._request(
            "PATCH",
            f"/api/v1/sessions/{session_id}",
            json={"status": status},
            headers=self._trace_headers(),
            retry_connect_errors=2,
        )

    async def forward_callback(self, callback_data: dict) -> dict[str, Any]:
        """Forward Executor callback to Backend and return the callback response."""
        response = await self._request(
            "POST",
            "/api/v1/callback",
            json=callback_data,
            headers=self._internal_headers(),
            retry_connect_errors=3,
        )
        data = response.json()
        result = data.get("data", {})
        return result if isinstance(result, dict) else {}

    async def claim_run(
        self,
        worker_id: str,
        lease_seconds: int = 30,
        schedule_modes: list[str] | None = None,
    ) -> dict | None:
        """Claim next run from backend queue."""
        payload: dict = {"worker_id": worker_id, "lease_seconds": lease_seconds}
        if schedule_modes:
            payload["schedule_modes"] = schedule_modes

        response = await self._request(
            "POST",
            "/api/v1/runs/claim",
            json=payload,
            headers=self._internal_headers(),
            retry_connect_errors=2,
        )
        data = response.json()
        return data.get("data")

    async def start_run(
        self, run_id: object, worker_id: str, lease_seconds: int | None = None
    ) -> dict:
        """Mark run as running."""
        payload: dict = {"worker_id": worker_id}
        if lease_seconds is not None:
            payload["lease_seconds"] = lease_seconds
        response = await self._request(
            "POST",
            f"/api/v1/runs/{run_id}/start",
            json=payload,
            headers=self._internal_headers(),
            retry_connect_errors=2,
        )
        data = response.json()
        return data["data"]

    async def fail_run(
        self, run_id: object, worker_id: str, error_message: str | None = None
    ) -> dict:
        """Mark run as failed."""
        response = await self._request(
            "POST",
            f"/api/v1/runs/{run_id}/fail",
            json={"worker_id": worker_id, "error_message": error_message},
            headers=self._internal_headers(),
            retry_connect_errors=2,
        )
        data = response.json()
        return data["data"]

    async def get_env_map(self, user_id: str) -> dict[str, str]:
        response = await self._request(
            "GET",
            "/api/v1/internal/env-vars/map",
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def resolve_mcp_config(
        self, user_id: str, server_ids: list[int]
    ) -> dict[str, object]:
        """Resolve effective MCP config for execution based on selected server ids."""
        response = await self._request(
            "POST",
            "/api/v1/internal/mcp-config/resolve",
            json={"server_ids": server_ids},
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def resolve_skill_config(
        self, user_id: str, skill_ids: list[int]
    ) -> dict[str, object]:
        """Resolve effective skill config for execution based on selected skill ids."""
        response = await self._request(
            "POST",
            "/api/v1/internal/skill-config/resolve",
            json={"skill_ids": skill_ids},
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def submit_skill_from_workspace(
        self,
        session_id: str,
        *,
        folder_path: str,
        skill_name: str | None,
        workspace_files_prefix: str,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/api/v1/internal/skills/submit-from-workspace",
            params={"session_id": session_id},
            json={
                "folder_path": folder_path,
                "skill_name": skill_name,
                "workspace_files_prefix": workspace_files_prefix,
            },
            headers=self._internal_headers(),
        )
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def resolve_plugin_config(
        self, user_id: str, plugin_ids: list[int]
    ) -> dict[str, object]:
        """Resolve effective plugin config for execution based on selected plugin ids."""
        response = await self._request(
            "POST",
            "/api/v1/internal/plugin-config/resolve",
            json={"plugin_ids": plugin_ids},
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def resolve_subagents(
        self, user_id: str, subagent_ids: list[int] | None
    ) -> dict[str, object]:
        """Resolve enabled subagents for execution based on selected ids.

        When `subagent_ids` is None, backend uses the user's enabled subagents
        as defaults. An explicit empty list means "disable all subagents".
        """
        payload: dict = {}
        if subagent_ids is not None:
            payload["subagent_ids"] = subagent_ids
        response = await self._request(
            "POST",
            "/api/v1/internal/subagents/resolve",
            json=payload,
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def get_execution_settings(self, user_id: str) -> dict[str, object]:
        response = await self._request(
            "GET",
            "/api/v1/internal/execution-settings/resolve",
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def update_run_metadata(
        self, run_id: str, metadata: dict[str, object]
    ) -> None:
        await self._request(
            "PATCH",
            f"/api/v1/internal/runs/{run_id}/metadata",
            headers=self._internal_headers(),
            json=metadata,
        )

    async def record_mcp_transition(
        self,
        *,
        run_id: str,
        session_id: str,
        server_name: str,
        to_state: str,
        event_source: str = "executor_manager",
        error_message: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record an MCP connection state transition via backend internal API."""
        await self._request(
            "POST",
            "/api/v1/internal/mcp-transitions",
            headers=self._internal_headers(),
            json={
                "run_id": run_id,
                "session_id": session_id,
                "server_name": server_name,
                "to_state": to_state,
                "event_source": event_source,
                "error_message": error_message,
                "metadata": metadata,
            },
            retry_connect_errors=1,
        )

    async def record_permission_audit(
        self,
        *,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_input: dict | None = None,
        policy_action: str = "allow",
        policy_rule_id: str | None = None,
        policy_reason: str | None = None,
        audit_mode: bool = True,
        context: dict | None = None,
    ) -> None:
        """Record a permission audit event via backend internal API."""
        await self._request(
            "POST",
            "/api/v1/internal/permission-audit",
            headers=self._internal_headers(),
            json={
                "run_id": run_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "policy_action": policy_action,
                "policy_rule_id": policy_rule_id,
                "policy_reason": policy_reason,
                "audit_mode": audit_mode,
                "context": context,
            },
            retry_connect_errors=1,
        )

    async def resolve_slash_commands(
        self,
        user_id: str,
        names: list[str] | None = None,
        skill_names: list[str] | None = None,
    ) -> dict[str, str]:
        """Resolve enabled slash commands for execution (rendered markdown)."""
        payload: dict = {"names": names or []}
        if skill_names is not None:
            payload["skill_names"] = skill_names
        response = await self._request(
            "POST",
            "/api/v1/internal/slash-commands/resolve",
            json=payload,
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        resolved = data.get("data", {}) or {}
        if not isinstance(resolved, dict):
            return {}
        return {str(k): str(v) for k, v in resolved.items() if isinstance(v, str)}

    async def get_claude_md(self, user_id: str) -> dict[str, object]:
        """Fetch user-level CLAUDE.md settings for execution staging."""
        response = await self._request(
            "GET",
            "/api/v1/internal/claude-md",
            headers=self._internal_user_headers(user_id),
        )
        data = response.json()
        result = data.get("data", {}) or {}
        return result if isinstance(result, dict) else {}

    async def dispatch_due_scheduled_tasks(self, limit: int = 50) -> dict:
        """Trigger backend to dispatch due scheduled tasks into the run queue."""
        payload = {"limit": max(1, int(limit))}
        response = await self._request(
            "POST",
            "/api/v1/internal/scheduled-tasks/dispatch-due",
            json=payload,
            headers=self._internal_headers(),
            retry_connect_errors=2,
        )
        data = response.json()
        return data.get("data", {}) or {}

    async def create_user_input_request(self, payload: dict) -> dict:
        response = await self._request(
            "POST",
            "/api/v1/internal/user-input-requests",
            json=payload,
            headers=self._internal_headers(),
        )
        data = response.json()
        return data["data"]

    async def get_user_input_request(self, request_id: str) -> dict:
        response = await self._request(
            "GET",
            f"/api/v1/internal/user-input-requests/{request_id}",
            headers=self._internal_headers(),
        )
        data = response.json()
        return data["data"]

    async def create_memory(self, session_id: str, payload: dict[str, Any]) -> Any:
        """Create memories via backend internal API."""
        response = await self._request(
            "POST",
            "/api/v1/internal/memories",
            params={"session_id": session_id},
            json=payload,
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def get_memory_create_job(self, session_id: str, job_id: str) -> Any:
        """Get memory create job status via backend internal API."""
        response = await self._request(
            "GET",
            f"/api/v1/internal/memories/jobs/{job_id}",
            params={"session_id": session_id},
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def list_memories(self, session_id: str) -> Any:
        """List memories via backend internal API."""
        response = await self._request(
            "GET",
            "/api/v1/internal/memories",
            params={"session_id": session_id},
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def search_memories(self, session_id: str, payload: dict[str, Any]) -> Any:
        """Search memories via backend internal API."""
        response = await self._request(
            "POST",
            "/api/v1/internal/memories/search",
            params={"session_id": session_id},
            json=payload,
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def get_memory(self, session_id: str, memory_id: str) -> Any:
        """Get a memory by id via backend internal API."""
        response = await self._request(
            "GET",
            f"/api/v1/internal/memories/{memory_id}",
            params={"session_id": session_id},
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def update_memory(
        self,
        session_id: str,
        memory_id: str,
        payload: dict[str, Any],
    ) -> Any:
        """Update a memory by id via backend internal API."""
        response = await self._request(
            "PUT",
            f"/api/v1/internal/memories/{memory_id}",
            params={"session_id": session_id},
            json=payload,
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def get_memory_history(self, session_id: str, memory_id: str) -> Any:
        """Get memory history via backend internal API."""
        response = await self._request(
            "GET",
            f"/api/v1/internal/memories/{memory_id}/history",
            params={"session_id": session_id},
            headers=self._internal_headers(),
        )
        data = response.json()
        return data.get("data")

    async def delete_memory(self, session_id: str, memory_id: str) -> dict[str, Any]:
        """Delete a memory by id via backend internal API."""
        response = await self._request(
            "DELETE",
            f"/api/v1/internal/memories/{memory_id}",
            params={"session_id": session_id},
            headers=self._internal_headers(),
        )
        data = response.json()
        result = data.get("data")
        return result if isinstance(result, dict) else {}

    async def delete_all_memories(self, session_id: str) -> dict[str, Any]:
        """Delete all memories in session scope via backend internal API."""
        response = await self._request(
            "DELETE",
            "/api/v1/internal/memories",
            params={"session_id": session_id},
            headers=self._internal_headers(),
        )
        data = response.json()
        result = data.get("data")
        return result if isinstance(result, dict) else {}
