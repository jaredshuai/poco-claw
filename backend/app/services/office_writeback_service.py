"""OnlyOffice save writeback use case helpers."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.office_edit_session import OfficeEditSession
from app.models.office_save_request import OfficeSaveRequest
from app.utils.workspace_manifest import find_manifest_file

logger = logging.getLogger(__name__)


class OfficeWritebackStateCommitError(RuntimeError):
    """Raised after storage writeback is committed but local state cannot be saved."""


class OfficeSaveWritebackService:
    """Commit a saved OnlyOffice document through a staged storage write."""

    def __init__(self, *, storage_service: Any, editing_store: Any) -> None:
        self.storage_service = storage_service
        self.editing_store = editing_store

    def commit_saved_content(
        self,
        db: Session,
        *,
        edit_session: OfficeEditSession,
        save_request: OfficeSaveRequest,
        content: bytes,
        content_type: str,
    ) -> None:
        writeback_object_key = (
            _build_office_writeback_object_key(
                current_object_key=edit_session.object_key,
                save_request_id=str(save_request.save_request_id),
            )
            if edit_session.manifest_key
            else edit_session.object_key
        )
        visible_writeback_committed = False

        try:
            self.storage_service.put_object(
                key=writeback_object_key,
                body=content,
                content_type=content_type,
            )

            # Marker: content is staged but manifest not yet flipped.
            # Commit it before any external side effect (manifest flip) so the
            # recovery marker is durable: if the process crashes after storage
            # points at the new object but before complete_save_request commits,
            # recover_staged_writebacks() can still replay from this marker.
            self.editing_store.mark_staged(
                db,
                save_request.save_request_id,
                staged_object_key=writeback_object_key,
            )
            db.commit()

            if edit_session.manifest_key:
                metadata = (
                    self.storage_service.get_object_metadata(writeback_object_key) or {}
                )
                self._update_manifest_file_metadata(
                    manifest_key=edit_session.manifest_key,
                    file_path=edit_session.file_path,
                    object_key=writeback_object_key,
                    metadata=metadata,
                    content_size=len(content),
                )
                visible_writeback_committed = True
            else:
                visible_writeback_committed = True

            try:
                self.editing_store.complete_save_request(
                    db,
                    save_request.save_request_id,
                    edit_session_id=edit_session.edit_session_id,
                    object_key=writeback_object_key,
                )
            except Exception as exc:
                if visible_writeback_committed:
                    raise OfficeWritebackStateCommitError(
                        "Office writeback storage commit succeeded, but save state commit failed"
                    ) from exc
                raise
        except OfficeWritebackStateCommitError:
            raise
        except Exception:
            if edit_session.manifest_key and not visible_writeback_committed:
                self._delete_staged_object(writeback_object_key)
            raise

    def _delete_staged_object(self, object_key: str) -> None:
        delete_object = getattr(self.storage_service, "delete_object", None)
        if delete_object is None:
            return
        try:
            delete_object(object_key)
        except Exception as exc:
            logger.warning(
                "Failed to clean up staged Office writeback object %s: %s",
                object_key,
                exc,
            )

    def _update_manifest_file_metadata(
        self,
        *,
        manifest_key: str,
        file_path: str,
        object_key: str,
        metadata: dict[str, Any],
        content_size: int,
    ) -> None:
        manifest = self.storage_service.get_manifest(manifest_key)
        file_entry = find_manifest_file(manifest, file_path)
        if file_entry is None:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Saved file is missing from workspace manifest",
            )

        file_entry["key"] = object_key
        file_entry["size"] = metadata.get("content_length") or content_size
        if metadata.get("etag"):
            file_entry["etag"] = metadata["etag"]
        if metadata.get("last_modified"):
            file_entry["last_modified"] = _json_safe(metadata["last_modified"])

        self.storage_service.put_object(
            key=manifest_key,
            body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_office_writeback_object_key(
    *,
    current_object_key: str,
    save_request_id: str,
) -> str:
    safe_save_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in save_request_id
    )
    object_path = PurePosixPath(current_object_key)
    file_name = object_path.name or "document"
    parent = str(object_path.parent)
    if parent in {"", "."}:
        return f".office-saves/{safe_save_id}/{file_name}"
    return f"{parent}/.office-saves/{safe_save_id}/{file_name}"
