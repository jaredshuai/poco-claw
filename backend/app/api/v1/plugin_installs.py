from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_plugin_install import (
    UserPluginInstallBulkUpdateRequest,
    UserPluginInstallBulkUpdateResponse,
    UserPluginInstallCreateRequest,
    UserPluginInstallResponse,
    UserPluginInstallUpdateRequest,
)
from app.services.user_plugin_install_service import UserPluginInstallService

router = APIRouter(prefix="/plugin-installs", tags=["plugin-installs"])

service = UserPluginInstallService()


@router.get("", response_model=ResponseSchema[list[UserPluginInstallResponse]])
async def list_plugin_installs(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.list_installs(db, actor.user_id)
    return Response.success(data=result, message="Plugin installs retrieved")


@router.post("", response_model=ResponseSchema[UserPluginInstallResponse])
async def create_plugin_install(
    request: UserPluginInstallCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.create_install(db, actor.user_id, request)
    return Response.success(data=result, message="Plugin install created")


@router.patch(
    "/bulk", response_model=ResponseSchema[UserPluginInstallBulkUpdateResponse]
)
async def bulk_update_plugin_installs(
    request: UserPluginInstallBulkUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.bulk_update_installs(db, actor.user_id, request)
    return Response.success(data=result, message="Plugin installs updated")


@router.patch("/{install_id}", response_model=ResponseSchema[UserPluginInstallResponse])
async def update_plugin_install(
    install_id: int,
    request: UserPluginInstallUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update_install(db, actor.user_id, install_id, request)
    return Response.success(data=result, message="Plugin install updated")


@router.delete("/{install_id}", response_model=ResponseSchema[dict])
async def delete_plugin_install(
    install_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service.delete_install(db, actor.user_id, install_id)
    return Response.success(data={"id": install_id}, message="Plugin install deleted")
