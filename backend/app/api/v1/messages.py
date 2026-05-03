from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db, get_policy_engine
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyEngine
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
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Gets a message by ID."""
    message = message_service.get_message(db, message_id)
    db_session = session_service.get_session(db, message.session_id)
    decision = policy_engine.can_access_user_resource(actor, db_session.user_id)
    if not decision.allowed:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Message does not belong to the user",
        )
    return Response.success(
        data=message_service.get_message_response(
            db, message_id, user_id=actor.user_id
        ),
        message="Message retrieved successfully",
    )
