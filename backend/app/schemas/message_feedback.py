from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

MessageFeedbackVote = Literal["like", "dislike", "none"]


class MessageFeedbackRequest(BaseModel):
    """Request payload for persisting message feedback."""

    vote: MessageFeedbackVote


class MessageFeedbackResponse(BaseModel):
    """Message feedback response."""

    message_id: int
    vote: MessageFeedbackVote
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
