import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_executor_manager
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_input_request import (
    UserInputRequestCreateRequest,
    UserInputRequestResponse,
)
from app.services.user_input_request_service import UserInputRequestService

router = APIRouter(prefix="/internal", tags=["internal"])

user_input_service = UserInputRequestService()


@router.post(
    "/user-input-requests",
    response_model=ResponseSchema[UserInputRequestResponse],
)
async def create_user_input_request(
    request: UserInputRequestCreateRequest,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = user_input_service.create_request(db, request)
    return Response.success(data=result, message="User input request created")


@router.get(
    "/user-input-requests/{request_id}",
    response_model=ResponseSchema[UserInputRequestResponse],
)
async def get_user_input_request(
    request_id: uuid.UUID,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = user_input_service.get_request(db, request_id=str(request_id))
    return Response.success(data=result, message="User input request retrieved")
