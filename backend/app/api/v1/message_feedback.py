from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.schemas.message_feedback import MessageFeedbackRequest, MessageFeedbackResponse
from app.schemas.response import Response, ResponseSchema
from app.services.message_feedback_service import MessageFeedbackService

router = APIRouter(prefix="/messages", tags=["messages"])

message_feedback_service = MessageFeedbackService()


@router.put(
    "/{message_id}/feedback",
    response_model=ResponseSchema[MessageFeedbackResponse],
)
async def upsert_message_feedback(
    message_id: int,
    request: MessageFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Persists a feedback vote for an owned assistant message."""
    feedback = message_feedback_service.set_feedback(
        db,
        user_id=user_id,
        message_id=message_id,
        vote=request.vote,
    )
    return Response.success(
        data=MessageFeedbackResponse.model_validate(feedback),
        message="Message feedback saved successfully",
    )
