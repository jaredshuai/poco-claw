import uuid
from typing import Literal

from pydantic import BaseModel, Field


class OfficeViewerConfigRequest(BaseModel):
    """Request body for generating an OnlyOffice viewer config."""

    session_id: uuid.UUID = Field(..., description="Session that owns the file")
    file_path: str = Field(
        ..., description="Relative path of the file within the workspace"
    )
    file_type: str | None = Field(
        default=None,
        description="Explicit file extension (doc/docx/xls/xlsx/ppt/pptx). Auto-detected from file_path if omitted.",
    )
    language: str = Field(default="en", description="Editor UI language (e.g. en, zh)")
    mode: Literal["view", "edit"] = Field(
        default="view",
        description="OnlyOffice mode. `edit` creates a short-lived edit session.",
    )
    edit_session_id: str | None = Field(
        default=None,
        description="Existing edit session to reuse when reopening the same file.",
    )


class OfficeDocumentConfig(BaseModel):
    """OnlyOffice document descriptor."""

    fileType: str
    key: str
    title: str
    url: str


class OfficeEditorConfig(BaseModel):
    """OnlyOffice editor configuration."""

    mode: str = "view"
    lang: str = "en"
    callbackUrl: str | None = None
    user: dict[str, str] | None = None


class OfficeViewerConfigResponse(BaseModel):
    """Full OnlyOffice config payload returned to the frontend."""

    document: OfficeDocumentConfig
    documentType: str
    editorConfig: OfficeEditorConfig
    token: str = Field(..., description="JWT token for the Document Server")
    type: str = "embedded"
    edit_session_id: str | None = None


class OfficeForceSaveRequest(BaseModel):
    """Request body for forcing the active OnlyOffice editor to save."""

    session_id: uuid.UUID
    file_path: str
    edit_session_id: str


class OfficeForceSaveResponse(BaseModel):
    """Response returned after the command service accepts a force-save request."""

    save_request_id: str
    status: Literal["pending", "saving"] = "saving"
    poll_after_ms: int = 1000


class OfficeSaveStatusResponse(BaseModel):
    """Short-lived save request status returned to the frontend poller."""

    save_request_id: str
    status: Literal["pending", "saving", "saved", "failed"]
    error_code: str | None = None
    error_message: str | None = None
    completed_at: str | None = None


class OfficeDiscardEditSessionRequest(BaseModel):
    """Request body for discarding an active Office edit session."""

    session_id: uuid.UUID
    file_path: str
    edit_session_id: str


class OfficeDiscardEditSessionResponse(BaseModel):
    """Response returned after an edit session is discarded."""

    edit_session_id: str
    status: Literal["discarded"] = "discarded"


class OfficeDownloadLatestResponse(BaseModel):
    """Short-lived download URL for the latest workspace object version."""

    url: str
    file_path: str
    expires_in: int


class OfficeCallbackRequest(BaseModel):
    """OnlyOffice callback payload subset used by Poco."""

    status: int
    key: str
    url: str | None = None
    userdata: str | None = None
    error: int | None = None
    token: str | None = None
