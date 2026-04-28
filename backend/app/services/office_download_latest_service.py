"""OnlyOffice latest workspace file download use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_workspace_file_resolver import (
    OfficeWorkspaceFileQuery,
    OfficeWorkspaceFileResolver,
)
from app.utils.workspace_manifest import normalize_manifest_path


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

        workspace_file = OfficeWorkspaceFileResolver(
            storage_service=self.storage_service
        ).resolve(
            OfficeWorkspaceFileQuery(
                manifest_key=command.workspace_manifest_key,
                files_prefix=command.workspace_files_prefix,
                file_path=command.file_path,
            )
        )
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
