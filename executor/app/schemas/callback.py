from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.clock import utc_now
from app.schemas.enums import CallbackStatus
from app.schemas.state import AgentCurrentState


class AgentCallbackRequest(BaseModel):
    """Callback request sent during agent execution."""

    session_id: str
    run_id: str | None = None
    time: datetime = Field(default_factory=utc_now)
    status: CallbackStatus
    progress: int
    error_message: str | None = None
    new_message: Optional[Any] = None
    state_patch: Optional[AgentCurrentState] = None
    sdk_session_id: Optional[str] = None
