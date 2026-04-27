"""User account profile and credits (backed by `user_accounts`)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_account import UserMePayload
from app.services.user_account_service import UserAccountService

router = APIRouter(prefix="/users", tags=["users"])

user_account_service = UserAccountService()


@router.get("/me", response_model=ResponseSchema[UserMePayload])
async def get_current_account(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Returns profile and credits for the resolved current user."""
    data = user_account_service.get_me(db, user_id)
    return Response.success(data=data, message="User account retrieved")
