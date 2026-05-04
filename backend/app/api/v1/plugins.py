from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.plugin import PluginCreateRequest, PluginResponse, PluginUpdateRequest
from app.schemas.response import Response, ResponseSchema
from app.services.plugin_service import PluginService

router = APIRouter(prefix="/plugins", tags=["plugins"])

service = PluginService()


@router.get("", response_model=ResponseSchema[list[PluginResponse]])
async def list_plugins(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.list_plugins(db, user_id=actor.user_id)
    return Response.success(data=result, message="Plugins retrieved")


@router.get("/{plugin_id}", response_model=ResponseSchema[PluginResponse])
async def get_plugin(
    plugin_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.get_plugin(db, actor.user_id, plugin_id)
    return Response.success(data=result, message="Plugin retrieved")


@router.post("", response_model=ResponseSchema[PluginResponse])
async def create_plugin(
    request: PluginCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.create_plugin(db, actor.user_id, request)
    return Response.success(data=result, message="Plugin created")


@router.patch("/{plugin_id}", response_model=ResponseSchema[PluginResponse])
async def update_plugin(
    plugin_id: int,
    request: PluginUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update_plugin(db, actor.user_id, plugin_id, request)
    return Response.success(data=result, message="Plugin updated")


@router.delete("/{plugin_id}", response_model=ResponseSchema[dict])
async def delete_plugin(
    plugin_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service.delete_plugin(db, actor.user_id, plugin_id)
    return Response.success(data={"id": plugin_id}, message="Plugin deleted")
