"""Office document preview endpoints (OnlyOffice integration)."""

import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.settings import get_settings
from app.schemas.office import OfficeViewerConfigRequest, OfficeViewerConfigResponse
from app.schemas.response import Response
from app.services.office_viewer_service import build_viewer_config
from app.services.session_service import SessionService
from app.services.storage_service import S3StorageService
from app.utils.workspace_manifest import (
    extract_manifest_files,
    normalize_manifest_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/office", tags=["office"])

session_service = SessionService()
storage_service = S3StorageService()


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
        db_session, request.file_path,
    )

    # Server-side file size enforcement.  The manifest may include a ``size``
    # field; fall back to an S3 HeadObject request when it does not.
    settings = get_settings()
    size_limit = settings.office_file_size_limit_mb * 1024 * 1024
    file_size = manifest_size
    if file_size is None:
        file_size = storage_service.get_object_size(object_key)
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

    file_name = request.file_path.rsplit("/", 1)[-1] if "/" in request.file_path else request.file_path

    return build_viewer_config(
        file_name=file_name,
        presigned_url=presigned_url,
        object_key=object_key,
        file_type=request.file_type,
        language=request.language,
    )


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
