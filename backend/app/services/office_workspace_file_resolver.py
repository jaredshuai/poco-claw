"""Resolve Office workspace files from a workspace manifest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.utils.workspace_manifest import extract_manifest_files, normalize_manifest_path


class OfficeWorkspaceManifestStorage(Protocol):
    def get_manifest(self, key: str) -> Any: ...


@dataclass(frozen=True)
class OfficeWorkspaceFileQuery:
    manifest_key: str | None
    files_prefix: str | None
    file_path: str


@dataclass(frozen=True)
class OfficeWorkspaceFile:
    object_key: str
    mime_type: str | None
    file_size: int | None


class OfficeWorkspaceFileResolver:
    """Look up a workspace file object key and metadata from the manifest."""

    def __init__(self, *, storage_service: OfficeWorkspaceManifestStorage) -> None:
        self.storage_service = storage_service

    def resolve(self, query: OfficeWorkspaceFileQuery) -> OfficeWorkspaceFile:
        if not query.manifest_key:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Workspace export not ready",
            )

        manifest = self.storage_service.get_manifest(query.manifest_key)
        manifest_files = extract_manifest_files(manifest)
        prefix = (query.files_prefix or "").rstrip("/")
        normalized_target = normalize_manifest_path(query.file_path) or query.file_path

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
            _enforce_workspace_prefix(
                object_key=object_key,
                prefix=prefix,
                file_path=query.file_path,
            )
            return OfficeWorkspaceFile(
                object_key=object_key,
                mime_type=file_entry.get("mimeType") or file_entry.get("mime_type"),
                file_size=_parse_file_size(file_entry.get("size")),
            )

        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message=f"File not found in workspace: {query.file_path}",
        )


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


def _parse_file_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
