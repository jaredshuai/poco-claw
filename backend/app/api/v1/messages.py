from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.message import MessageResponse
from app.schemas.response import Response, ResponseSchema
from app.services.message_service import MessageService
from app.services.session_service import SessionService

router = APIRouter(prefix="/messages", tags=["messages"])

message_service = MessageService()
session_service = SessionService()


@router.get("/{message_id}", response_model=ResponseSchema[MessageResponse])
async def get_message(
    message_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Gets a message by ID."""
    message = message_service.get_message(db, message_id)
    db_session = session_service.get_session(db, message.session_id)
    if db_session.user_id != user_id:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Message does not belong to the user",
        )
    return Response.success(
        data=message_service.get_message_response(db, message_id, user_id=user_id),
        message="Message retrieved successfully",
    )
