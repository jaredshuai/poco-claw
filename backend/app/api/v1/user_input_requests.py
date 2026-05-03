import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_input_request import (
    UserInputAnswerRequest,
    UserInputRequestResponse,
)
from app.services.user_input_request_service import UserInputRequestService

router = APIRouter(prefix="/user-input-requests", tags=["user-input-requests"])

user_input_service = UserInputRequestService()


@router.get("", response_model=ResponseSchema[list[UserInputRequestResponse]])
async def list_pending_user_input_requests(
    actor: Actor = Depends(get_current_actor),
    session_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = user_input_service.list_pending_for_user(
        db, user_id=actor.user_id, session_id=session_id
    )
    return Response.success(data=result, message="User input requests retrieved")


@router.post(
    "/{request_id}/answer",
    response_model=ResponseSchema[UserInputRequestResponse],
)
async def answer_user_input_request(
    request_id: uuid.UUID,
    request: UserInputAnswerRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = user_input_service.answer_request(
        db, user_id=actor.user_id, request_id=str(request_id), answer_request=request
    )
    return Response.success(data=result, message="User input request answered")
