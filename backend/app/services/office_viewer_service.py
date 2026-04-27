"""Service for generating OnlyOffice Document Server viewer configs with JWT."""

import hashlib
import logging

import jwt

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.settings import get_settings
from app.schemas.office import (
    OfficeDocumentConfig,
    OfficeEditorConfig,
    OfficeViewerConfigResponse,
)

logger = logging.getLogger(__name__)

EXTENSION_TO_DOCUMENT_TYPE: dict[str, str] = {
    "doc": "word",
    "docx": "word",
    "xls": "cell",
    "xlsx": "cell",
    "ppt": "slide",
    "pptx": "slide",
}

SUPPORTED_EXTENSIONS = frozenset(EXTENSION_TO_DOCUMENT_TYPE.keys())


def detect_extension(file_name: str, explicit: str | None = None) -> str:
    """Detect the Office extension from *file_name* or an *explicit* override.

    The file-name extension always takes precedence over the caller-supplied
    *explicit* hint to prevent a client from mismatching the document type
    (e.g. sending ``file_type=pptx`` for ``report.docx``).

    The *explicit* hint is accepted **only** for files that have no extension
    at all (e.g. ``README``).  Files with a non-Office extension (e.g.
    ``image.png``) will not be overridden — they must be rejected.
    """
    # Prefer the extension derived from the actual file name
    dot_idx = file_name.rfind(".")
    has_extension = dot_idx != -1
    if has_extension:
        ext = file_name[dot_idx + 1 :].lower()
        if ext in SUPPORTED_EXTENSIONS:
            return ext

    # Accept the explicit hint ONLY for truly extensionless files
    if explicit and not has_extension:
        ext = explicit.lower().lstrip(".")
        if ext in SUPPORTED_EXTENSIONS:
            return ext

    raise AppException(
        error_code=ErrorCode.BAD_REQUEST,
        message="Unsupported or unrecognized Office file type",
    )


def generate_document_key(object_key: str, version: str | None = None) -> str:
    """Generate a deterministic document key from the canonical S3 object key.

    OnlyOffice uses *key* to identify a document for caching.  By hashing the
    stable object key (not the presigned URL which changes every request) the
    Document Server can reuse its conversion cache for the same file.

    When *version* is provided (e.g. an ETag or last-modified timestamp) it is
    included in the hash so that replaced files get a fresh cache key.
    """
    material = f"{object_key}:{version}" if version else object_key
    return hashlib.sha256(material.encode()).hexdigest()[:20]


def build_viewer_config(
    *,
    file_name: str,
    presigned_url: str,
    object_key: str,
    file_type: str | None = None,
    language: str = "en",
    document_version: str | None = None,
    mode: str = "view",
    callback_url: str | None = None,
    user_id: str | None = None,
) -> OfficeViewerConfigResponse:
    """Build an OnlyOffice viewer config and sign it with JWT.

    Parameters
    ----------
    file_name:
        Display title for the document.
    presigned_url:
        A fresh presigned GET URL that the Document Server can fetch.
    object_key:
        The stable S3 object key used to generate a cache-friendly document key.
    file_type:
        Optional explicit extension override.
    language:
        Editor UI language.
    document_version:
        Optional version tag (e.g. ETag or last-modified) to bust OnlyOffice cache.
    """

    settings = get_settings()
    secret = settings.office_jwt_secret
    if not secret:
        raise AppException(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="OFFICE_JWT_SECRET is not configured",
        )
    if len(secret.encode("utf-8")) < 32:
        raise AppException(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="OFFICE_JWT_SECRET must be at least 32 bytes for HS256",
        )

    ext = detect_extension(file_name, file_type)
    document_type = EXTENSION_TO_DOCUMENT_TYPE[ext]
    doc_key = generate_document_key(object_key, document_version)

    document = OfficeDocumentConfig(
        fileType=ext,
        key=doc_key,
        title=file_name,
        url=presigned_url,
    )

    editor_config = OfficeEditorConfig(
        mode=mode,
        lang=language,
        callbackUrl=callback_url,
        user={"id": user_id, "name": user_id} if user_id else None,
    )

    # Build the payload that will be signed as JWT
    config_payload: dict = {
        "document": document.model_dump(),
        "documentType": document_type,
        "editorConfig": editor_config.model_dump(exclude_none=True),
        "type": "embedded",
    }

    token = jwt.encode(config_payload, secret, algorithm="HS256")

    return OfficeViewerConfigResponse(
        document=document,
        documentType=document_type,
        editorConfig=editor_config,
        token=token,
    )
