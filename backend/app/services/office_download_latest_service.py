"""OnlyOffice latest workspace file download use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.utils.workspace_manifest import extract_manifest_files, normalize_manifest_path


class OfficeDownloadLatestStorage(Protocol):
    def get_manifest(self, key: str) -> Any: ...

    def get_object_metadata(self, key: str) -> dict[str, Any] | None: ...

    def presign_get(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        response_content_disposition: str | None = None,
        response_content_type: str | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class OfficeDownloadLatestCommand:
    session_id: str
    session_user_id: str
    user_id: str
    file_path: str
    workspace_manifest_key: str | None
    workspace_files_prefix: str | None
    expires_in: int


@dataclass(frozen=True)
class OfficeDownloadLatestResult:
    url: str
    file_path: str
    expires_in: int


@dataclass(frozen=True)
class _WorkspaceFile:
    object_key: str
    mime_type: str | None


class OfficeDownloadLatestUseCase:
    """Create a short-lived download URL for the latest saved workspace object."""

    def __init__(self, *, storage_service: OfficeDownloadLatestStorage) -> None:
        self.storage_service = storage_service

    def execute(
        self, command: OfficeDownloadLatestCommand
    ) -> OfficeDownloadLatestResult:
        if command.session_user_id != command.user_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Session does not belong to the user",
            )
        if not normalize_manifest_path(command.file_path):
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Invalid file path",
            )

        workspace_file = self._resolve_workspace_file(command)
        if self.storage_service.get_object_metadata(workspace_file.object_key) is None:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Workspace file is missing from storage: {command.file_path}",
            )

        file_name = (
            command.file_path.rsplit("/", 1)[-1]
            if "/" in command.file_path
            else command.file_path
        )
        safe_file_name = file_name.replace('"', "_")
        url = self.storage_service.presign_get(
            workspace_file.object_key,
            response_content_disposition=f'attachment; filename="{safe_file_name}"',
            response_content_type=workspace_file.mime_type
            or "application/octet-stream",
            expires_in=command.expires_in,
        )
        return OfficeDownloadLatestResult(
            url=url,
            file_path=command.file_path,
            expires_in=command.expires_in,
        )

    def _resolve_workspace_file(
        self,
        command: OfficeDownloadLatestCommand,
    ) -> _WorkspaceFile:
        if not command.workspace_manifest_key:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Workspace export not ready",
            )

        manifest = self.storage_service.get_manifest(command.workspace_manifest_key)
        manifest_files = extract_manifest_files(manifest)
        prefix = (command.workspace_files_prefix or "").rstrip("/")
        normalized_target = (
            normalize_manifest_path(command.file_path) or command.file_path
        )

        for file_entry in manifest_files:
            entry_path = normalize_manifest_path(file_entry.get("path"))
            if not entry_path or entry_path != normalized_target:
                continue
            object_key = (
                file_entry.get("key")
                or file_entry.get("object_key")
                or file_entry.get("oss_key")
                or file_entry.get("s3_key")
            )
            if not object_key and prefix:
                object_key = f"{prefix}/{entry_path.lstrip('/')}"
            if not object_key:
                continue
            self._enforce_workspace_prefix(
                object_key=object_key,
                prefix=prefix,
                file_path=command.file_path,
            )
            return _WorkspaceFile(
                object_key=object_key,
                mime_type=file_entry.get("mimeType") or file_entry.get("mime_type"),
            )

        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message=f"File not found in workspace: {command.file_path}",
        )

    @staticmethod
    def _enforce_workspace_prefix(
        *,
        object_key: str,
        prefix: str,
        file_path: str,
    ) -> None:
        if not prefix:
            return
        normalized_key = normalize_manifest_path(object_key) or object_key
        normalized_prefix = normalize_manifest_path(prefix) or prefix
        if normalized_key == normalized_prefix or normalized_key.startswith(
            f"{normalized_prefix}/"
        ):
            return
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Workspace manifest object key escapes workspace prefix",
            details={"file_path": file_path, "object_key": object_key},
        )
