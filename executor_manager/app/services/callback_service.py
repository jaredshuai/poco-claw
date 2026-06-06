import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol

from app.schemas.callback import AgentCallbackRequest, CallbackReceiveResponse
from app.services.backend_client import BackendClient
from app.services.clock import Clock, SystemClock
from app.services.workspace_export_service import (
    WorkspaceExportService,
    workspace_manager,
)
from app.services.worker_identity import get_worker_id

logger = logging.getLogger(__name__)


class CallbackBackendClient(Protocol):
    async def forward_callback(
        self, callback_data: Mapping[str, object]
    ) -> Mapping[str, object]: ...

    async def record_mcp_transition(
        self,
        *,
        run_id: str,
        session_id: str,
        server_name: str,
        to_state: str,
        event_source: str = "executor_manager",
        error_message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    async def record_permission_audit(
        self,
        *,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_input: dict[str, object] | None = None,
        policy_action: str = "allow",
        policy_rule_id: str | None = None,
        policy_reason: str | None = None,
        audit_mode: bool = True,
        context: dict[str, object] | None = None,
    ) -> None: ...


class CallbackWorkspaceExportService(Protocol):
    def export_workspace(self, session_id: str) -> Any: ...


class CallbackRuntimeCleanup(Protocol):
    async def on_task_complete(self, session_id: str) -> None: ...


class CallbackWorkspacePathFilter(Protocol):
    def is_ignored(self, path: str) -> bool: ...


def build_backend_client() -> CallbackBackendClient:
    return BackendClient()


@lru_cache(maxsize=1)
def get_backend_client() -> CallbackBackendClient:
    return build_backend_client()


def build_workspace_export_service() -> CallbackWorkspaceExportService:
    return WorkspaceExportService()


@lru_cache(maxsize=1)
def get_workspace_export_service() -> CallbackWorkspaceExportService:
    return build_workspace_export_service()


class TaskDispatcherRuntimeCleanup:
    async def on_task_complete(self, session_id: str) -> None:
        from app.scheduler.task_dispatcher import TaskDispatcher

        await TaskDispatcher.on_task_complete(session_id)


def is_ignored_workspace_path(path: str) -> bool:
    """Check whether a workspace-relative path should be ignored."""
    clean = (path or "").replace("\\", "/").strip()
    if not clean:
        return True

    # Normalise common prefixes while keeping the path relative.
    while clean.startswith("./"):
        clean = clean[2:]
    clean = clean.lstrip("/")

    parts = [p for p in clean.split("/") if p]
    if not parts:
        return True
    # Defensive: never allow traversal-like paths to leak into state.
    if any(p in (".", "..") for p in parts):
        return True

    ignore_names = workspace_manager._ignore_names
    ignore_dot = workspace_manager.ignore_dot_files

    for part in parts:
        if part in ignore_names:
            return True
        if ignore_dot and part.startswith("."):
            return True
    return False


class WorkspaceManagerPathFilter:
    def is_ignored(self, path: str) -> bool:
        return is_ignored_workspace_path(path)


def build_callback_runtime_cleanup() -> CallbackRuntimeCleanup:
    return TaskDispatcherRuntimeCleanup()


def build_callback_workspace_path_filter() -> CallbackWorkspacePathFilter:
    return WorkspaceManagerPathFilter()


class CallbackService:
    """Service layer for callback processing."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        backend_client_factory: Callable[[], CallbackBackendClient] | None = None,
        workspace_export_service_factory: Callable[[], CallbackWorkspaceExportService]
        | None = None,
        runtime_cleanup: CallbackRuntimeCleanup | None = None,
        runtime_cleanup_factory: Callable[[], CallbackRuntimeCleanup] | None = None,
        workspace_path_filter: CallbackWorkspacePathFilter | None = None,
        workspace_path_filter_factory: Callable[[], CallbackWorkspacePathFilter]
        | None = None,
        worker_id_provider: Callable[[], str] | None = None,
    ) -> None:
        self.clock = clock or SystemClock()
        self._backend_client_factory = backend_client_factory or get_backend_client
        self._workspace_export_service_factory = (
            workspace_export_service_factory or get_workspace_export_service
        )
        self._runtime_cleanup = runtime_cleanup
        self._runtime_cleanup_factory = (
            runtime_cleanup_factory or build_callback_runtime_cleanup
        )
        self._workspace_path_filter = workspace_path_filter
        self._workspace_path_filter_factory = (
            workspace_path_filter_factory or build_callback_workspace_path_filter
        )
        self._worker_id_provider = worker_id_provider or get_worker_id

    def _get_worker_id(self) -> str:
        return self._worker_id_provider()

    def _get_backend_client(self) -> CallbackBackendClient:
        return self._backend_client_factory()

    def _get_workspace_export_service(self) -> CallbackWorkspaceExportService:
        return self._workspace_export_service_factory()

    @property
    def runtime_cleanup(self) -> CallbackRuntimeCleanup:
        if self._runtime_cleanup is None:
            self._runtime_cleanup = self._runtime_cleanup_factory()
        return self._runtime_cleanup

    @runtime_cleanup.setter
    def runtime_cleanup(self, value: CallbackRuntimeCleanup) -> None:
        self._runtime_cleanup = value

    @property
    def workspace_path_filter(self) -> CallbackWorkspacePathFilter:
        if self._workspace_path_filter is None:
            self._workspace_path_filter = self._workspace_path_filter_factory()
        return self._workspace_path_filter

    @workspace_path_filter.setter
    def workspace_path_filter(self, value: CallbackWorkspacePathFilter) -> None:
        self._workspace_path_filter = value

    def _now_utc(self) -> datetime:
        now = self.clock.now_utc()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    @staticmethod
    def _is_internal_mcp_server(name: str) -> bool:
        clean = (name or "").strip()
        return clean.startswith("__poco_")

    @staticmethod
    def _is_ignored_workspace_path(path: str) -> bool:
        """Check whether a workspace-relative path should be ignored.

        This keeps /sessions state_patch.workspace_state.file_changes consistent with the
        workspace export/list ignore policy in executor_manager WorkspaceManager.
        """
        return is_ignored_workspace_path(path)

    @staticmethod
    def _normalize_metadata(metadata: Any) -> dict[str, object] | None:
        """Normalize metadata payload to dict[str, object] | None."""
        if isinstance(metadata, dict):
            return dict(metadata)
        return None

    @staticmethod
    def _normalize_tool_input(tool_input: Any) -> dict[str, object] | None:
        """Normalize tool_input payload to dict[str, object] | None."""
        if isinstance(tool_input, dict):
            return dict(tool_input)
        return None

    @staticmethod
    def _normalize_context(context: Any) -> dict[str, object] | None:
        """Normalize context payload to dict[str, object] | None."""
        if isinstance(context, dict):
            return dict(context)
        return None

    @classmethod
    def _filter_state_patch(
        cls,
        callback: AgentCallbackRequest,
        *,
        is_ignored_path: Callable[[str], bool] | None = None,
    ) -> AgentCallbackRequest:
        state = callback.state_patch
        if not state:
            return callback

        updated_state = state

        # Hide built-in/internal MCP servers from the UI. End users should only see
        # explicitly configured MCP servers.
        if state.mcp_status:
            filtered_mcp = [
                m
                for m in state.mcp_status
                if not cls._is_internal_mcp_server(m.server_name)
            ]
            if len(filtered_mcp) != len(state.mcp_status):
                updated_state = updated_state.model_copy(
                    update={"mcp_status": filtered_mcp}
                )

        workspace_state = updated_state.workspace_state
        if not workspace_state or not workspace_state.file_changes:
            return (
                callback
                if updated_state is state
                else callback.model_copy(update={"state_patch": updated_state})
            )
        file_changes = workspace_state.file_changes
        path_filter = is_ignored_path or cls._is_ignored_workspace_path

        filtered_changes = [fc for fc in file_changes if not path_filter(fc.path)]
        if len(filtered_changes) == len(file_changes):
            return (
                callback
                if updated_state is state
                else callback.model_copy(update={"state_patch": updated_state})
            )

        total_added = sum(fc.added_lines for fc in filtered_changes)
        total_deleted = sum(fc.deleted_lines for fc in filtered_changes)

        new_workspace_state = workspace_state.model_copy(
            update={
                "file_changes": filtered_changes,
                "total_added_lines": total_added,
                "total_deleted_lines": total_deleted,
            }
        )
        updated_state = updated_state.model_copy(
            update={"workspace_state": new_workspace_state}
        )
        return callback.model_copy(update={"state_patch": updated_state})

    async def process_callback(
        self, callback: AgentCallbackRequest
    ) -> CallbackReceiveResponse:
        """Process agent execution callback from executor.

        Args:
            callback: Callback data from executor

        Returns:
            CallbackReceiveResponse with acknowledgment

        Raises:
            AppException: If callback forwarding to backend fails
        """
        from app.core.errors.error_codes import ErrorCode
        from app.core.errors.exceptions import AppException

        # Handle special message types (mcp_transition, permission_audit)
        new_message = callback.new_message
        if isinstance(new_message, dict):
            msg_type = new_message.get("type")
            if msg_type == "mcp_transition":
                await self._handle_mcp_transition(callback)
                return CallbackReceiveResponse(
                    status="received",
                    session_id=callback.session_id,
                    callback_status=callback.status,
                    progress=callback.progress,
                )
            if msg_type == "permission_audit":
                await self._handle_permission_audit(callback)
                return CallbackReceiveResponse(
                    status="received",
                    session_id=callback.session_id,
                    callback_status=callback.status,
                    progress=callback.progress,
                )

        # High-frequency callbacks: keep RUNNING as DEBUG; only completed/failed stay at INFO.
        summary_level = (
            logging.INFO
            if callback.status in ["completed", "failed"]
            else logging.DEBUG
        )
        logger.log(
            summary_level,
            "callback_received",
            extra={
                "session_id": callback.session_id,
                "status": callback.status,
                "progress": callback.progress,
                "sdk_session_id": callback.sdk_session_id,
                "run_id": callback.run_id,
            },
        )

        callback = self._filter_state_patch(
            callback,
            is_ignored_path=self.workspace_path_filter.is_ignored,
        )

        if callback.state_patch:
            state = callback.state_patch
            todo_count = len(state.todos) if state.todos else 0
            mcp_count = len(state.mcp_status) if state.mcp_status else 0
            file_count = (
                len(state.workspace_state.file_changes) if state.workspace_state else 0
            )
            logger.debug(
                "callback_state_patch_summary",
                extra={
                    "session_id": callback.session_id,
                    "todo_count": todo_count,
                    "mcp_count": mcp_count,
                    "file_change_count": file_count,
                },
            )

        try:
            payload_model = callback
            if callback.status in ["completed", "failed"]:
                payload_model = callback.model_copy(
                    update={"workspace_export_status": "pending"}
                )

            # Inject worker_id if available and not already present
            if payload_model.worker_id is None:
                worker_id = self._get_worker_id()
                if worker_id is not None:
                    payload_model = payload_model.model_copy(
                        update={"worker_id": worker_id}
                    )

            payload = payload_model.model_dump(mode="json")

            # Forward callback to backend
            backend = self._get_backend_client()
            backend_response = await backend.forward_callback(payload)

            if callback.status in ["completed", "failed"]:
                logger.info(
                    "task_terminal_callback_received",
                    extra={
                        "session_id": callback.session_id,
                        "status": callback.status,
                        "run_id": callback.run_id,
                        "session_status": backend_response.get("status"),
                    },
                )
                asyncio.create_task(self._export_and_forward(callback))
                session_status = str(backend_response.get("status") or "").strip()
                if session_status not in {"pending", "running"}:
                    await self.runtime_cleanup.on_task_complete(callback.session_id)
                else:
                    logger.info(
                        "task_cleanup_deferred",
                        extra={
                            "session_id": callback.session_id,
                            "status": callback.status,
                            "run_id": callback.run_id,
                            "session_status": session_status,
                        },
                    )

            return CallbackReceiveResponse(
                status="received",
                session_id=callback.session_id,
                callback_status=callback.status,
                progress=callback.progress,
            )

        except Exception:
            logger.exception(
                "callback_forward_failed",
                extra={"session_id": callback.session_id, "status": callback.status},
            )
            raise AppException(
                error_code=ErrorCode.CALLBACK_FORWARD_FAILED,
                message="Failed to forward callback to backend",
            )

    async def _handle_mcp_transition(self, callback: AgentCallbackRequest) -> None:
        """Forward MCP transition event to backend internal API."""
        new_message = callback.new_message
        if not isinstance(new_message, dict):
            return
        try:
            backend = self._get_backend_client()
            await backend.record_mcp_transition(
                run_id=callback.run_id or "",
                session_id=callback.session_id,
                server_name=str(new_message.get("server_name") or ""),
                to_state=str(new_message.get("to_state") or ""),
                event_source=str(new_message.get("event_source") or "executor"),
                error_message=new_message.get("error_message"),
                metadata=self._normalize_metadata(new_message.get("metadata")),
            )
        except Exception:
            logger.debug(
                "mcp_transition_forward_failed",
                extra={
                    "session_id": callback.session_id,
                    "run_id": callback.run_id,
                },
            )

    async def _handle_permission_audit(self, callback: AgentCallbackRequest) -> None:
        """Forward permission audit event to backend internal API."""
        new_message = callback.new_message
        if not isinstance(new_message, dict):
            return
        try:
            backend = self._get_backend_client()
            await backend.record_permission_audit(
                run_id=callback.run_id or "",
                session_id=callback.session_id,
                tool_name=str(new_message.get("tool_name") or ""),
                tool_input=self._normalize_tool_input(new_message.get("tool_input")),
                policy_action=str(new_message.get("policy_action") or "allow"),
                policy_rule_id=new_message.get("policy_rule_id"),
                policy_reason=new_message.get("policy_reason"),
                audit_mode=bool(new_message.get("audit_mode", True)),
                context=self._normalize_context(new_message.get("context")),
            )
        except Exception:
            logger.debug(
                "permission_audit_forward_failed",
                extra={
                    "session_id": callback.session_id,
                    "run_id": callback.run_id,
                },
            )

    async def _export_and_forward(self, callback: AgentCallbackRequest) -> None:
        try:
            exporter = self._get_workspace_export_service()
            result = await asyncio.to_thread(
                exporter.export_workspace, callback.session_id
            )
        except Exception:
            logger.exception(
                "workspace_export_failed",
                extra={"session_id": callback.session_id},
            )
            result = None

        payload_model = AgentCallbackRequest(
            session_id=callback.session_id,
            run_id=callback.run_id,
            worker_id=callback.worker_id or self._get_worker_id(),
            time=self._now_utc(),
            status=callback.status,
            progress=100 if callback.status == "completed" else callback.progress,
            error_message=callback.error_message,
            sdk_session_id=callback.sdk_session_id,
            workspace_files_prefix=result.workspace_files_prefix if result else None,
            workspace_manifest_key=result.workspace_manifest_key if result else None,
            workspace_archive_key=result.workspace_archive_key if result else None,
            workspace_export_status=(
                result.workspace_export_status if result else "failed"
            ),
        )
        payload = payload_model.model_dump(mode="json")

        try:
            backend = self._get_backend_client()
            await backend.forward_callback(payload)
        except Exception:
            logger.exception(
                "workspace_export_callback_forward_failed",
                extra={"session_id": callback.session_id},
            )
