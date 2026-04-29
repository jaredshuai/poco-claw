"""OnlyOffice viewer-config use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import quote

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeViewerConfigResponse
from app.services.id_generator import IdGenerator, UuidIdGenerator
from app.services.office_editing_service import OfficeEditSession
from app.services.office_viewer_service import build_viewer_config
from app.services.office_workspace_file_resolver import (
    OfficeWorkspaceFile,
    OfficeWorkspaceFileQuery,
    OfficeWorkspaceFileResolver,
)
from app.utils.workspace_manifest import normalize_manifest_path


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


class OfficeViewerConfigUseCase:
    """Build a signed OnlyOffice viewer/editor config for a workspace file."""

    def __init__(
        self,
        *,
        storage_service: OfficeViewerConfigStorage,
        editing_store: OfficeViewerConfigEditingStore,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self.storage_service = storage_service
        self.editing_store = editing_store
        self.id_generator = id_generator or UuidIdGenerator()

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

        workspace_file = OfficeWorkspaceFileResolver(
            storage_service=self.storage_service
        ).resolve(
            OfficeWorkspaceFileQuery(
                manifest_key=command.workspace_manifest_key,
                files_prefix=command.workspace_files_prefix,
                file_path=command.file_path,
            )
        )
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
        workspace_file: OfficeWorkspaceFile,
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
            edit_session_id = command.edit_session_id or self.id_generator.new_id()
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


def _build_callback_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/office/callback?token={quote(token)}"
