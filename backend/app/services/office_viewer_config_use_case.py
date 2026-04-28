"""OnlyOffice viewer-config use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import quote
import uuid

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeViewerConfigResponse
from app.services.office_editing_service import OfficeEditSession
from app.services.office_viewer_service import build_viewer_config
from app.utils.workspace_manifest import extract_manifest_files, normalize_manifest_path


class OfficeViewerConfigStorage(Protocol):
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


class OfficeViewerConfigEditingStore(Protocol):
    def create_edit_session(
        self,
        *,
        session_id: str,
        user_id: str,
        file_path: str,
        object_key: str,
        mime_type: str | None,
        manifest_key: str | None,
        document_key: str,
        edit_session_id: str | None = None,
    ) -> OfficeEditSession: ...


@dataclass(frozen=True)
class OfficeViewerConfigCommand:
    session_id: str
    session_user_id: str
    user_id: str
    file_path: str
    file_type: str | None
    language: str
    mode: Literal["view", "edit"]
    edit_session_id: str | None
    workspace_manifest_key: str | None
    workspace_files_prefix: str | None
    file_size_limit_bytes: int
    presign_expires_in: int
    callback_base_url: str


@dataclass(frozen=True)
class _WorkspaceFile:
    object_key: str
    mime_type: str | None
    file_size: int | None


class OfficeViewerConfigUseCase:
    """Build a signed OnlyOffice viewer/editor config for a workspace file."""

    def __init__(
        self,
        *,
        storage_service: OfficeViewerConfigStorage,
        editing_store: OfficeViewerConfigEditingStore,
    ) -> None:
        self.storage_service = storage_service
        self.editing_store = editing_store

    def execute(self, command: OfficeViewerConfigCommand) -> OfficeViewerConfigResponse:
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
        metadata = self.storage_service.get_object_metadata(workspace_file.object_key)
        if metadata is None:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Workspace file is missing from storage: {command.file_path}",
            )
        file_size = (
            workspace_file.file_size
            if workspace_file.file_size is not None
            else metadata.get("content_length")
        )
        if file_size is not None and file_size > command.file_size_limit_bytes:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="File is too large for online preview",
            )

        presigned_url = self.storage_service.presign_get(
            workspace_file.object_key,
            response_content_disposition="inline",
            response_content_type=workspace_file.mime_type
            or "application/octet-stream",
            expires_in=command.presign_expires_in,
        )
        return self._build_config(
            command=command,
            workspace_file=workspace_file,
            metadata=metadata,
            file_size=file_size,
            presigned_url=presigned_url,
        )

    def _build_config(
        self,
        *,
        command: OfficeViewerConfigCommand,
        workspace_file: _WorkspaceFile,
        metadata: dict[str, Any],
        file_size: int | None,
        presigned_url: str,
    ) -> OfficeViewerConfigResponse:
        file_name = (
            command.file_path.rsplit("/", 1)[-1]
            if "/" in command.file_path
            else command.file_path
        )
        document_version = (
            metadata.get("etag")
            or str(metadata.get("last_modified") or "")
            or str(file_size)
        )
        edit_session_id = None
        document_version_for_key = document_version or None
        if command.mode == "edit":
            edit_session_id = command.edit_session_id or str(uuid.uuid4())
            document_version_for_key = (
                f"{document_version}:{edit_session_id}"
                if document_version
                else edit_session_id
            )

        config = build_viewer_config(
            file_name=file_name,
            presigned_url=presigned_url,
            object_key=workspace_file.object_key,
            file_type=command.file_type,
            language=command.language,
            document_version=document_version_for_key,
            mode=command.mode,
            user_id=command.user_id if command.mode == "edit" else None,
        )

        if command.mode != "edit":
            return config

        edit_session = self.editing_store.create_edit_session(
            session_id=command.session_id,
            user_id=command.user_id,
            file_path=command.file_path,
            object_key=workspace_file.object_key,
            mime_type=workspace_file.mime_type,
            manifest_key=command.workspace_manifest_key,
            document_key=config.document.key,
            edit_session_id=edit_session_id,
        )
        config = build_viewer_config(
            file_name=file_name,
            presigned_url=presigned_url,
            object_key=workspace_file.object_key,
            file_type=command.file_type,
            language=command.language,
            document_version=document_version_for_key,
            mode=command.mode,
            callback_url=_build_callback_url(
                command.callback_base_url,
                edit_session.callback_token,
            ),
            user_id=command.user_id,
        )
        config.edit_session_id = edit_session.edit_session_id
        return config

    def _resolve_workspace_file(
        self,
        command: OfficeViewerConfigCommand,
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
                file_size=_parse_file_size(file_entry.get("size")),
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


def _build_callback_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/office/callback?token={quote(token)}"


def _parse_file_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
