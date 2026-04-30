import re
from collections.abc import Callable
from typing import Protocol

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.computer import ComputerScreenshotUploadResponse
from app.services.storage_service import S3StorageService
from app.services.workspace_manager import WorkspaceManager


_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")


class ComputerStorage(Protocol):
    def put_object(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str | None = None,
    ) -> None: ...


def build_computer_storage() -> ComputerStorage:
    return S3StorageService()


def build_computer_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


def _sanitize_token(value: str) -> str:
    token = (value or "").strip()
    token = _SAFE_TOKEN.sub("_", token)
    token = token.strip("._-")
    return token or "unknown"


class ComputerService:
    """Service layer for Poco Computer artifacts (screenshots, recordings, etc.)."""

    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager | None = None,
        storage_service: ComputerStorage | None = None,
        storage_service_factory: Callable[[], ComputerStorage] | None = None,
        workspace_manager_factory: Callable[[], WorkspaceManager] | None = None,
    ) -> None:
        storage_factory = storage_service_factory or build_computer_storage
        workspace_factory = (
            workspace_manager_factory or build_computer_workspace_manager
        )
        self._workspace_manager = (
            workspace_manager if workspace_manager is not None else workspace_factory()
        )
        self._storage_service = (
            storage_service if storage_service is not None else storage_factory()
        )

    def upload_browser_screenshot(
        self,
        *,
        session_id: str,
        tool_use_id: str,
        content_type: str,
        data: bytes,
    ) -> ComputerScreenshotUploadResponse:
        user_id = self._workspace_manager.resolve_user_id(session_id)
        if not user_id:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Unable to resolve user_id for session",
                details={"session_id": session_id},
            )

        safe_session_id = _sanitize_token(session_id)
        safe_tool_use_id = _sanitize_token(tool_use_id)

        # Keep the key deterministic so the frontend can map (session_id, tool_use_id) -> screenshot.
        key = f"replays/{user_id}/{safe_session_id}/browser/{safe_tool_use_id}.png"

        self._storage_service.put_object(
            key=key,
            body=data,
            content_type=content_type or "image/png",
        )

        return ComputerScreenshotUploadResponse(
            session_id=session_id,
            tool_use_id=tool_use_id,
            key=key,
            content_type=content_type or "image/png",
            size_bytes=len(data),
        )
