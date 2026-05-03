"""User account profile and credits (backed by `user_accounts`)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_account import UserMePayload
from app.services.user_account_service import UserAccountService

router = APIRouter(prefix="/users", tags=["users"])

user_account_service = UserAccountService()


@router.get("/me", response_model=ResponseSchema[UserMePayload])
async def get_current_account(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Returns profile and credits for the resolved current user."""
    data = user_account_service.get_me(db, actor.user_id)
    return Response.success(data=data, message="User account retrieved")
