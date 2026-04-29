import os
import re

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.core.deps import get_current_user_id
from app.core.settings import get_settings
from app.schemas.input_file import InputFile
from app.schemas.response import Response, ResponseSchema
from app.services.id_generator import IdGenerator, UuidIdGenerator
from app.services.storage_service import S3StorageService

router = APIRouter(prefix="/attachments", tags=["attachments"])

storage_service: S3StorageService | None = None
id_generator = UuidIdGenerator()

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


def _normalize_upload_filename(filename: str) -> str:
    """Normalize an upload filename for display and workspace staging."""
    raw = (filename or "").strip().replace("\\", "/")
    raw = raw.split("/")[-1].strip()

    # Many multipart parsers decode header bytes as latin-1. If the client actually
    # sent UTF-8 bytes, this results in mojibake. Best-effort fix.
    try:
        raw = raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    raw = _CONTROL_CHARS.sub("", raw).strip()
    return raw or "upload.bin"


def _get_file_size(file: UploadFile) -> int | None:
    try:
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        return size
    except Exception:
        return None


def get_attachment_id_generator() -> IdGenerator:
    return id_generator


def get_storage_service() -> S3StorageService:
    global storage_service
    if storage_service is None:
        storage_service = S3StorageService()
    return storage_service


@router.post("/upload", response_model=ResponseSchema[InputFile])
async def upload_attachment(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    id_generator: IdGenerator = Depends(get_attachment_id_generator),
    storage_service: S3StorageService = Depends(get_storage_service),
) -> JSONResponse:
    """Upload a user attachment to storage."""
    settings = get_settings()
    max_size_bytes = settings.max_upload_size_mb * 1024 * 1024

    original_name = _normalize_upload_filename(file.filename or "")
    attachment_id = id_generator.new_id()
    # Use a stable object name to avoid any encoding/sanitization issues with filenames.
    key = f"attachments/{user_id}/{attachment_id}/file"

    size = _get_file_size(file)
    if size is not None and size > max_size_bytes:
        return Response.error(
            code=413,
            message=f"File too large. Max {settings.max_upload_size_mb}MB.",
            data={"max_bytes": max_size_bytes, "actual_bytes": size},
            status_code=413,
        )

    storage_service.upload_fileobj(
        fileobj=file.file,
        key=key,
        content_type=file.content_type,
    )

    payload = InputFile(
        id=attachment_id,
        type="file",
        name=original_name,
        source=key,
        size=size,
        content_type=file.content_type,
    )
    return Response.success(data=payload, message="Attachment uploaded successfully")
