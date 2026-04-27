"""Office document preview and editing endpoints (OnlyOffice integration)."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote, urlparse

import httpx
import jwt
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.settings import get_settings
from app.schemas.office import (
    OfficeCallbackRequest,
    OfficeDiscardEditSessionRequest,
    OfficeDiscardEditSessionResponse,
    OfficeDownloadLatestResponse,
    OfficeForceSaveRequest,
    OfficeForceSaveResponse,
    OfficeSaveStatusResponse,
    OfficeViewerConfigRequest,
    OfficeViewerConfigResponse,
)
from app.schemas.response import Response
from app.services.office_editing_service import (
    OnlyOfficeCommandClient,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_SAVED,
    office_editing_store,
)
from app.services.office_viewer_service import build_viewer_config
from app.services.session_service import SessionService
from app.services.storage_service import S3StorageService
from app.utils.workspace_manifest import (
    extract_manifest_files,
    find_manifest_file,
    normalize_manifest_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/office", tags=["office"])

session_service = SessionService()
storage_service = S3StorageService()
editing_store = office_editing_store
command_client = OnlyOfficeCommandClient()


def _resolve_file_object_key(
    db_session,
    file_path: str,
) -> tuple[str, str | None, int | None]:
    """Look up the S3 object key, MIME type, and size for *file_path*.

    Returns ``(object_key, mime_type, file_size)``.  *file_size* may be
    ``None`` when the manifest does not include a ``size`` field.
    Raises ``AppException`` if the file is not found in the manifest.
    """
    if not db_session.workspace_manifest_key:
        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message="Workspace export not ready",
        )

    manifest = storage_service.get_manifest(db_session.workspace_manifest_key)
    manifest_files = extract_manifest_files(manifest)
    prefix = (db_session.workspace_files_prefix or "").rstrip("/")
    normalized_target = normalize_manifest_path(file_path) or file_path

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
        # Enforce workspace prefix boundary: reject keys that escape the
        # current session's workspace scope (prevents cross-session access).
        if prefix:
            normalized_key = normalize_manifest_path(object_key) or object_key
            normalized_prefix = normalize_manifest_path(prefix) or prefix
            if not (
                normalized_key == normalized_prefix
                or normalized_key.startswith(f"{normalized_prefix}/")
            ):
                raise AppException(
                    error_code=ErrorCode.FORBIDDEN,
                    message="Workspace manifest object key escapes workspace prefix",
                    details={"file_path": file_path, "object_key": object_key},
                )
        mime_type = file_entry.get("mimeType") or file_entry.get("mime_type")
        file_size = file_entry.get("size")
        if file_size is not None:
            try:
                file_size = int(file_size)
            except (ValueError, TypeError):
                file_size = None
        return object_key, mime_type, file_size

    raise AppException(
        error_code=ErrorCode.NOT_FOUND,
        message=f"File not found in workspace: {file_path}",
    )


def _build_callback_url(token: str) -> str:
    settings = get_settings()
    base_url = settings.office_callback_base_url.rstrip("/")
    return f"{base_url}/office/callback?token={quote(token)}"


def _origin_tuple(raw_url: str) -> tuple[str, str, int] | None:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, parsed.hostname.lower(), port


def _validate_callback_download_url(raw_url: str) -> None:
    """Allow callback file downloads only from the configured Document Server."""
    settings = get_settings()
    document_server_origin = _origin_tuple(settings.office_document_server_url)
    callback_url_origin = _origin_tuple(raw_url)
    if (
        document_server_origin is None
        or callback_url_origin is None
        or document_server_origin != callback_url_origin
    ):
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="OnlyOffice callback download URL is not trusted",
        )


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _decode_callback_payload(
    raw_body: dict,
    authorization: str | None,
) -> dict:
    """Validate OnlyOffice callback JWT and return the signed payload."""
    body_token = raw_body.get("token")
    onlyoffice_token = (
        body_token if isinstance(body_token, str) and body_token.strip() else None
    ) or _extract_bearer_token(authorization)

    settings = get_settings()
    if not onlyoffice_token:
        if settings.office_callback_jwt_required:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="OnlyOffice callback JWT is missing",
            )
        return {key: value for key, value in raw_body.items() if key != "token"}

    if not settings.office_jwt_secret:
        raise AppException(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="OFFICE_JWT_SECRET is not configured",
        )

    try:
        decoded = jwt.decode(
            onlyoffice_token,
            settings.office_jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="OnlyOffice callback JWT is invalid",
        ) from exc

    if not isinstance(decoded, dict):
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="OnlyOffice callback JWT payload is invalid",
        )

    signed_payload = decoded.get("payload")
    payload = signed_payload if isinstance(signed_payload, dict) else decoded
    if not isinstance(payload, dict):
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="OnlyOffice callback JWT payload is invalid",
        )

    for field in ("status", "key", "url", "userdata", "error"):
        if field in raw_body and field in payload and raw_body[field] != payload[field]:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="OnlyOffice callback JWT payload mismatch",
            )

    return payload


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _update_manifest_file_metadata(
    *,
    manifest_key: str,
    file_path: str,
    object_key: str,
    metadata: dict,
    content_size: int,
) -> None:
    manifest = storage_service.get_manifest(manifest_key)
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

    storage_service.put_object(
        key=manifest_key,
        body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )


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


@router.post("/viewer-config")
async def get_viewer_config(
    request: OfficeViewerConfigRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeViewerConfigResponse:
    """Generate a signed OnlyOffice viewer config for read-only preview.

    The backend verifies the session belongs to the calling user, resolves the
    file inside the workspace manifest, generates a fresh presigned URL, and
    returns the complete OnlyOffice config with JWT signature.
    """
    db_session = session_service.get_session(db, request.session_id)
    if db_session.user_id != user_id:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Session does not belong to the user",
        )

    # normalize_manifest_path returns None for paths containing '..' or '.'
    # segments, which is the canonical path-safety check in this codebase.
    if not normalize_manifest_path(request.file_path):
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="Invalid file path",
        )

    object_key, mime_type, manifest_size = _resolve_file_object_key(
        db_session,
        request.file_path,
    )

    # Server-side file size enforcement.  The manifest may include a ``size``
    # field; fall back to an S3 HeadObject request when it does not.
    # Fail fast if the object does not exist in storage at all.
    settings = get_settings()
    size_limit = settings.office_file_size_limit_mb * 1024 * 1024
    metadata = storage_service.get_object_metadata(object_key)
    if metadata is None:
        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message=f"Workspace file is missing from storage: {request.file_path}",
        )
    file_size = (
        manifest_size if manifest_size is not None else metadata["content_length"]
    )
    if file_size is not None and file_size > size_limit:
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="File is too large for online preview",
        )
    presigned_url = storage_service.presign_get(
        object_key,
        response_content_disposition="inline",
        response_content_type=mime_type or "application/octet-stream",
        expires_in=settings.office_presign_expires_seconds,
    )

    file_name = (
        request.file_path.rsplit("/", 1)[-1]
        if "/" in request.file_path
        else request.file_path
    )
    document_version = (
        metadata.get("etag")
        or str(metadata.get("last_modified") or "")
        or str(file_size)
    )

    edit_session_id = None
    callback_url = None
    document_version_for_key = document_version or None
    if request.mode == "edit":
        edit_session_id = request.edit_session_id or str(uuid.uuid4())
        document_version_for_key = (
            f"{document_version}:{edit_session_id}"
            if document_version
            else edit_session_id
        )

    config = build_viewer_config(
        file_name=file_name,
        presigned_url=presigned_url,
        object_key=object_key,
        file_type=request.file_type,
        language=request.language,
        document_version=document_version_for_key,
        mode=request.mode,
        user_id=user_id if request.mode == "edit" else None,
    )

    if request.mode == "edit":
        edit_session = editing_store.create_edit_session(
            session_id=str(request.session_id),
            user_id=user_id,
            file_path=request.file_path,
            object_key=object_key,
            mime_type=mime_type,
            manifest_key=db_session.workspace_manifest_key,
            document_key=config.document.key,
            edit_session_id=edit_session_id,
        )
        callback_url = _build_callback_url(edit_session.callback_token)
        config = build_viewer_config(
            file_name=file_name,
            presigned_url=presigned_url,
            object_key=object_key,
            file_type=request.file_type,
            language=request.language,
            document_version=document_version_for_key,
            mode=request.mode,
            callback_url=callback_url,
            user_id=user_id,
        )
        config.edit_session_id = edit_session.edit_session_id

    return config


@router.get("/download-latest")
async def download_latest(
    session_id: uuid.UUID = Query(...),
    file_path: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeDownloadLatestResponse:
    """Return a short-lived URL for the latest saved workspace file."""
    db_session = session_service.get_session(db, session_id)
    if db_session.user_id != user_id:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Session does not belong to the user",
        )

    if not normalize_manifest_path(file_path):
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="Invalid file path",
        )

    object_key, mime_type, _manifest_size = _resolve_file_object_key(
        db_session,
        file_path,
    )
    if storage_service.get_object_metadata(object_key) is None:
        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message=f"Workspace file is missing from storage: {file_path}",
        )

    settings = get_settings()
    file_name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    safe_file_name = file_name.replace('"', "_")
    url = storage_service.presign_get(
        object_key,
        response_content_disposition=f'attachment; filename="{safe_file_name}"',
        response_content_type=mime_type or "application/octet-stream",
        expires_in=settings.office_presign_expires_seconds,
    )
    return OfficeDownloadLatestResponse(
        url=url,
        file_path=file_path,
        expires_in=settings.office_presign_expires_seconds,
    )


@router.post("/forcesave")
async def force_save(
    request: OfficeForceSaveRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeForceSaveResponse:
    """Trigger an explicit OnlyOffice force-save for an active edit session."""
    db_session = session_service.get_session(db, request.session_id)
    if db_session.user_id != user_id:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Session does not belong to the user",
        )

    edit_session = editing_store.get_edit_session(request.edit_session_id)
    if (
        edit_session is None
        or edit_session.session_id != str(request.session_id)
        or normalize_manifest_path(edit_session.file_path)
        != normalize_manifest_path(request.file_path)
        or edit_session.user_id != user_id
    ):
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="Invalid or expired Office edit session",
        )

    active = editing_store.get_active_save_request(edit_session.edit_session_id)
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "save_in_progress",
                "active_save_request_id": active.save_request_id,
            },
        )

    save_request = editing_store.create_save_request(edit_session)
    try:
        await command_client.forcesave(
            document_key=edit_session.document_key,
            userdata=save_request.save_request_id,
        )
    except Exception as exc:
        editing_store.mark_failed(
            save_request.save_request_id,
            error_code="office_command_rejected",
            error_message=str(exc),
        )
        raise

    editing_store.mark_saving(save_request.save_request_id)
    return OfficeForceSaveResponse(
        save_request_id=save_request.save_request_id,
        status="saving",
    )


@router.get("/save-status")
async def get_save_status(
    session_id: uuid.UUID = Query(...),
    save_request_id: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeSaveStatusResponse:
    """Return a short-lived Office save request status."""
    del db
    save_request = editing_store.get_save_request(save_request_id)
    if save_request is None or save_request.session_id != str(session_id):
        return OfficeSaveStatusResponse(
            save_request_id=save_request_id,
            status=SAVE_STATUS_FAILED,
            error_code="not_found_or_expired",
        )

    if save_request.user_id != user_id:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Save request does not belong to the user",
        )

    return OfficeSaveStatusResponse(
        save_request_id=save_request.save_request_id,
        status=save_request.status,  # type: ignore[arg-type]
        error_code=save_request.error_code,
        error_message=save_request.error_message,
        completed_at=save_request.completed_at.isoformat()
        if save_request.completed_at
        else None,
    )


@router.post("/edit-session/discard")
async def discard_edit_session(
    request: OfficeDiscardEditSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeDiscardEditSessionResponse:
    """Discard an active Office edit session and revoke its callback token."""
    db_session = session_service.get_session(db, request.session_id)
    if db_session.user_id != user_id:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Session does not belong to the user",
        )

    edit_session = editing_store.get_edit_session(request.edit_session_id)
    if (
        edit_session is None
        or edit_session.session_id != str(request.session_id)
        or normalize_manifest_path(edit_session.file_path)
        != normalize_manifest_path(request.file_path)
        or edit_session.user_id != user_id
    ):
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="Invalid or expired Office edit session",
        )

    editing_store.discard_edit_session(edit_session.edit_session_id)
    return OfficeDiscardEditSessionResponse(
        edit_session_id=edit_session.edit_session_id,
    )


@router.post("/callback")
async def office_callback(
    request: dict = Body(...),
    token: str = Query(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    """Handle OnlyOffice save callbacks without browser-session auth."""
    callback_payload = _decode_callback_payload(request, authorization)
    try:
        callback = OfficeCallbackRequest.model_validate(callback_payload)
    except ValidationError as exc:
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="Invalid OnlyOffice callback payload",
        ) from exc

    edit_session = editing_store.resolve_by_token(token)
    if edit_session is None:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Invalid Office callback token",
        )
    if callback.key != edit_session.document_key:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Office callback document key mismatch",
        )

    if callback.status == 6:
        if not callback.userdata:
            return {"error": 0}
        save_request = editing_store.get_save_request(callback.userdata)
        if (
            save_request is None
            or save_request.edit_session_id != edit_session.edit_session_id
        ):
            return {"error": 0}
        if save_request.status in {SAVE_STATUS_SAVED, SAVE_STATUS_FAILED}:
            return {"error": 0}
        if not callback.url:
            editing_store.mark_failed(
                save_request.save_request_id,
                error_code="office_callback_missing_url",
            )
            return {"error": 0}

        try:
            _validate_callback_download_url(callback.url)
        except AppException:
            editing_store.mark_failed(
                save_request.save_request_id,
                error_code="untrusted_callback_download_url",
            )
            raise

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(callback.url)
                response.raise_for_status()
                content = response.content

            content_type = (
                response.headers.get("content-type")
                or edit_session.mime_type
                or "application/octet-stream"
            )
            writeback_object_key = (
                _build_office_writeback_object_key(
                    current_object_key=edit_session.object_key,
                    save_request_id=save_request.save_request_id,
                )
                if edit_session.manifest_key
                else edit_session.object_key
            )
            storage_service.put_object(
                key=writeback_object_key,
                body=content,
                content_type=content_type,
            )

            if edit_session.manifest_key:
                metadata = (
                    storage_service.get_object_metadata(writeback_object_key) or {}
                )
                _update_manifest_file_metadata(
                    manifest_key=edit_session.manifest_key,
                    file_path=edit_session.file_path,
                    object_key=writeback_object_key,
                    metadata=metadata,
                    content_size=len(content),
                )
                editing_store.update_edit_session_object_key(
                    edit_session.edit_session_id,
                    writeback_object_key,
                )

            editing_store.mark_saved(save_request.save_request_id)
        except Exception as exc:
            editing_store.mark_failed(
                save_request.save_request_id,
                error_code="writeback_failed",
                error_message=str(exc),
            )
            raise

    elif callback.status == 7 and callback.userdata:
        save_request = editing_store.get_save_request(callback.userdata)
        if (
            save_request is None
            or save_request.edit_session_id != edit_session.edit_session_id
        ):
            return {"error": 0}
        editing_store.mark_failed(
            save_request.save_request_id,
            error_code="office_forcesave_failed",
            error_message=str(callback.error) if callback.error is not None else None,
        )

    return {"error": 0}


@router.get("/health")
async def office_health(
    user_id: str = Depends(get_current_user_id),
):
    """Proxy health check to the OnlyOffice Document Server."""
    settings = get_settings()
    ds_url = settings.office_document_server_url
    if not ds_url:
        return Response.error(
            code=50201,
            message="OnlyOffice Document Server URL is not configured",
            status_code=503,
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ds_url.rstrip('/')}/healthcheck")
            healthy = resp.status_code == 200 and resp.text.strip().lower() == "true"
    except httpx.ConnectError:
        logger.warning("OnlyOffice Document Server is unreachable")
        healthy = False
    except httpx.TimeoutException:
        logger.warning("OnlyOffice Document Server health check timed out")
        healthy = False
    except Exception:
        logger.warning("OnlyOffice Document Server health check failed", exc_info=True)
        healthy = False

    if healthy:
        return Response.success(data={"status": "healthy"})

    return Response.error(
        code=50201,
        message="OnlyOffice Document Server is not healthy",
        status_code=503,
    )
