from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_skill_install import (
    UserSkillInstallBulkUpdateRequest,
    UserSkillInstallBulkUpdateResponse,
    UserSkillInstallCreateRequest,
    UserSkillInstallResponse,
    UserSkillInstallUpdateRequest,
)
from app.services.user_skill_install_service import UserSkillInstallService

router = APIRouter(prefix="/skill-installs", tags=["skill-installs"])

service = UserSkillInstallService()


@router.get("", response_model=ResponseSchema[list[UserSkillInstallResponse]])
async def list_skill_installs(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.list_installs(db, actor.user_id)
    return Response.success(data=result, message="Skill installs retrieved")


@router.post("", response_model=ResponseSchema[UserSkillInstallResponse])
async def create_skill_install(
    request: UserSkillInstallCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.create_install(db, actor.user_id, request)
    return Response.success(data=result, message="Skill install created")


@router.patch(
    "/bulk", response_model=ResponseSchema[UserSkillInstallBulkUpdateResponse]
)
async def bulk_update_skill_installs(
    request: UserSkillInstallBulkUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.bulk_update_installs(db, actor.user_id, request)
    return Response.success(data=result, message="Skill installs updated")


@router.patch("/{install_id}", response_model=ResponseSchema[UserSkillInstallResponse])
async def update_skill_install(
    install_id: int,
    request: UserSkillInstallUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update_install(db, actor.user_id, install_id, request)
    return Response.success(data=result, message="Skill install updated")


@router.delete("/{install_id}", response_model=ResponseSchema[dict])
async def delete_skill_install(
    install_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service.delete_install(db, actor.user_id, install_id)
    return Response.success(data={"id": install_id}, message="Skill install deleted")
