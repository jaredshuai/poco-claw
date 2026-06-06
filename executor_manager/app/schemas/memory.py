import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MemoryMessage(BaseModel):
    """Memory message payload."""

    role: str = Field(..., description="Role of the message.")
    content: str = Field(..., description="Message content.")


class MemoryCreateRequest(BaseModel):
    """Request to create memories in session scope."""

    session_id: str = Field(..., description="Session identifier.")
    messages: list[MemoryMessage] = Field(
        ...,
        min_length=1,
        description="Conversation messages used to extract and store memories.",
    )
    metadata: dict[str, object] | None = None


class MemorySearchRequest(BaseModel):
    """Request to search memories in session scope."""

    session_id: str = Field(..., description="Session identifier.")
    query: str = Field(..., description="Search query.")
    filters: dict[str, object] | None = None


class MemoryUpdateRequest(BaseModel):
    """Request to update memory in session scope."""

    session_id: str = Field(..., description="Session identifier.")
    text: str = Field(..., min_length=1, description="Updated memory text.")
    metadata: dict[str, object] | None = Field(
        default=None,
        description="Optional metadata for update operations.",
    )


class MemoryCreateJobEnqueueResponse(BaseModel):
    """Response for enqueueing a memory creation job."""

    job_id: uuid.UUID
    status: str


class MemoryCreateJobResponse(BaseModel):
    """Status response for a memory creation job."""

    job_id: uuid.UUID
    status: str
    progress: int = 0
    result: object | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
