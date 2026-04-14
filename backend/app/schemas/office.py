import uuid

from pydantic import BaseModel, Field


class OfficeViewerConfigRequest(BaseModel):
    """Request body for generating an OnlyOffice viewer config."""

    session_id: uuid.UUID = Field(..., description="Session that owns the file")
    file_path: str = Field(..., description="Relative path of the file within the workspace")
    file_type: str | None = Field(
        default=None,
        description="Explicit file extension (doc/docx/xls/xlsx/ppt/pptx). Auto-detected from file_path if omitted.",
    )
    language: str = Field(default="en", description="Editor UI language (e.g. en, zh)")


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


class OfficeViewerConfigResponse(BaseModel):
    """Full OnlyOffice config payload returned to the frontend."""

    document: OfficeDocumentConfig
    documentType: str
    editorConfig: OfficeEditorConfig
    token: str = Field(..., description="JWT token for the Document Server")
    type: str = "embedded"
