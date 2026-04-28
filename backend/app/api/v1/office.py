"""Office document preview and editing endpoints (OnlyOffice integration)."""

import logging
import uuid
from typing import Annotated
from urllib.parse import urlparse

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
from app.services.office_callback_service import OfficeCallbackUseCase
from app.services.office_discard_edit_session_service import (
    OfficeDiscardEditSessionCommand,
    OfficeDiscardEditSessionUseCase,
)
from app.services.office_download_latest_service import (
    OfficeDownloadLatestCommand,
    OfficeDownloadLatestUseCase,
)
from app.services.office_editing_service import (
    OnlyOfficeCommandClient,
    office_editing_store,
)
from app.services.office_force_save_service import (
    OfficeForceSaveCommand,
    OfficeForceSaveUseCase,
    OfficeSaveInProgressError,
)
from app.services.office_save_status_service import (
    OfficeSaveStatusQuery,
    OfficeSaveStatusUseCase,
)
from app.services.office_viewer_config_use_case import (
    OfficeViewerConfigCommand,
    OfficeViewerConfigUseCase,
)
from app.services.session_service import SessionService
from app.services.storage_service import S3StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/office", tags=["office"])

session_service = SessionService()
storage_service = S3StorageService()
editing_store = office_editing_store
command_client = OnlyOfficeCommandClient()


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
    settings = get_settings()
    return OfficeViewerConfigUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
    ).execute(
        OfficeViewerConfigCommand(
            session_id=str(request.session_id),
            session_user_id=db_session.user_id,
            user_id=user_id,
            file_path=request.file_path,
            file_type=request.file_type,
            language=request.language,
            mode=request.mode,
            edit_session_id=request.edit_session_id,
            workspace_manifest_key=db_session.workspace_manifest_key,
            workspace_files_prefix=db_session.workspace_files_prefix,
            file_size_limit_bytes=settings.office_file_size_limit_mb * 1024 * 1024,
            presign_expires_in=settings.office_presign_expires_seconds,
            callback_base_url=settings.office_callback_base_url,
        )
    )


@router.get("/download-latest")
async def download_latest(
    session_id: uuid.UUID = Query(...),
    file_path: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeDownloadLatestResponse:
    """Return a short-lived URL for the latest saved workspace file."""
    db_session = session_service.get_session(db, session_id)
    settings = get_settings()
    result = OfficeDownloadLatestUseCase(storage_service=storage_service).execute(
        OfficeDownloadLatestCommand(
            session_id=str(session_id),
            session_user_id=db_session.user_id,
            user_id=user_id,
            file_path=file_path,
            workspace_manifest_key=db_session.workspace_manifest_key,
            workspace_files_prefix=db_session.workspace_files_prefix,
            expires_in=settings.office_presign_expires_seconds,
        )
    )

    return OfficeDownloadLatestResponse(
        url=result.url,
        file_path=result.file_path,
        expires_in=result.expires_in,
    )


@router.post("/forcesave")
async def force_save(
    request: OfficeForceSaveRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeForceSaveResponse:
    """Trigger an explicit OnlyOffice force-save for an active edit session."""
    db_session = session_service.get_session(db, request.session_id)
    try:
        result = await OfficeForceSaveUseCase(
            editing_store=editing_store,
            command_client=command_client,
        ).execute(
            OfficeForceSaveCommand(
                session_id=str(request.session_id),
                session_user_id=db_session.user_id,
                user_id=user_id,
                file_path=request.file_path,
                edit_session_id=request.edit_session_id,
            )
        )
    except OfficeSaveInProgressError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "save_in_progress",
                "active_save_request_id": exc.active_save_request_id,
            },
        ) from exc

    return OfficeForceSaveResponse(
        save_request_id=result.save_request_id,
        status=result.status,
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
    result = OfficeSaveStatusUseCase(editing_store=editing_store).execute(
        OfficeSaveStatusQuery(
            session_id=str(session_id),
            save_request_id=save_request_id,
            user_id=user_id,
        )
    )

    return OfficeSaveStatusResponse(
        save_request_id=result.save_request_id,
        status=result.status,
        error_code=result.error_code,
        error_message=result.error_message,
        completed_at=result.completed_at,
    )


@router.post("/edit-session/discard")
async def discard_edit_session(
    request: OfficeDiscardEditSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OfficeDiscardEditSessionResponse:
    """Discard an active Office edit session and revoke its callback token."""
    db_session = session_service.get_session(db, request.session_id)
    result = OfficeDiscardEditSessionUseCase(editing_store=editing_store).execute(
        OfficeDiscardEditSessionCommand(
            session_id=str(request.session_id),
            session_user_id=db_session.user_id,
            user_id=user_id,
            file_path=request.file_path,
            edit_session_id=request.edit_session_id,
        )
    )
    return OfficeDiscardEditSessionResponse(
        edit_session_id=result.edit_session_id,
        status=result.status,
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

    await OfficeCallbackUseCase(
        storage_service=storage_service,
        editing_store=editing_store,
        validate_download_url=_validate_callback_download_url,
    ).handle(
        token=token,
        callback=callback,
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
