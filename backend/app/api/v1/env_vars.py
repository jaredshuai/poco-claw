from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.env_var import (
    EnvVarCreateRequest,
    EnvVarPublicResponse,
    EnvVarUpdateRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.env_var_service import EnvVarService

router = APIRouter(prefix="/env-vars", tags=["env-vars"])

env_var_service = EnvVarService()


@router.get("", response_model=ResponseSchema[list[EnvVarPublicResponse]])
async def list_env_vars(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = env_var_service.list_public_env_vars(db, user_id=actor.user_id)
    return Response.success(data=result, message="Env vars retrieved")


@router.post("", response_model=ResponseSchema[EnvVarPublicResponse])
async def create_env_var(
    request: EnvVarCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = env_var_service.create_user_env_var(db, actor.user_id, request)
    return Response.success(data=result, message="Env var created")


@router.patch("/{env_var_id}", response_model=ResponseSchema[EnvVarPublicResponse])
async def update_env_var(
    env_var_id: int,
    request: EnvVarUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = env_var_service.update_user_env_var(db, actor.user_id, env_var_id, request)
    return Response.success(data=result, message="Env var updated")


@router.delete("/{env_var_id}", response_model=ResponseSchema[dict])
async def delete_env_var(
    env_var_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    env_var_service.delete_user_env_var(db, actor.user_id, env_var_id)
    return Response.success(data={"id": env_var_id}, message="Env var deleted")
