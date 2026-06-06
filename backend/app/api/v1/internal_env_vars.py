from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db,
    get_internal_actor,
    require_executor_manager,
    require_internal_token,
)
from app.core.identity import Actor
from app.schemas.env_var import (
    SystemEnvVarCreateRequest,
    SystemEnvVarResponse,
    SystemEnvVarUpdateRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.env_var_service import EnvVarService

router = APIRouter(prefix="/internal", tags=["internal"])

env_var_service = EnvVarService()


@router.get("/env-vars/map", response_model=ResponseSchema[dict[str, str]])
async def get_env_map(
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    env_map = env_var_service.get_env_map(db, user_id=actor.user_id)
    return Response.success(data=env_map, message="Env map retrieved")


@router.get(
    "/system-env-vars",
    response_model=ResponseSchema[list[SystemEnvVarResponse]],
)
async def list_system_env_vars(
    _: None = Depends(require_internal_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = env_var_service.list_system_env_vars(db)
    return Response.success(data=result, message="System env vars retrieved")


@router.post(
    "/system-env-vars",
    response_model=ResponseSchema[SystemEnvVarResponse],
)
async def create_system_env_var(
    request: SystemEnvVarCreateRequest,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = env_var_service.create_system_env_var(db, request)
    return Response.success(data=result, message="System env var created")


@router.patch(
    "/system-env-vars/{env_var_id}",
    response_model=ResponseSchema[SystemEnvVarResponse],
)
async def update_system_env_var(
    env_var_id: int,
    request: SystemEnvVarUpdateRequest,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = env_var_service.update_system_env_var(db, env_var_id, request)
    return Response.success(data=result, message="System env var updated")


@router.delete(
    "/system-env-vars/{env_var_id}",
    response_model=ResponseSchema[dict],
)
async def delete_system_env_var(
    env_var_id: int,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    env_var_service.delete_system_env_var(db, env_var_id)
    return Response.success(data={"id": env_var_id}, message="System env var deleted")
