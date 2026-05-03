from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_mcp_install import (
    UserMcpInstallBulkUpdateRequest,
    UserMcpInstallBulkUpdateResponse,
    UserMcpInstallCreateRequest,
    UserMcpInstallResponse,
    UserMcpInstallUpdateRequest,
)
from app.services.user_mcp_install_service import UserMcpInstallService

router = APIRouter(prefix="/mcp-installs", tags=["mcp-installs"])

service = UserMcpInstallService()


@router.get("", response_model=ResponseSchema[list[UserMcpInstallResponse]])
async def list_user_mcp_installs(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.list_installs(db, actor.user_id)
    return Response.success(data=result, message="MCP installs retrieved")


@router.post("", response_model=ResponseSchema[UserMcpInstallResponse])
async def create_user_mcp_install(
    request: UserMcpInstallCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.create_install(db, actor.user_id, request)
    return Response.success(data=result, message="MCP install created")


@router.patch("/bulk", response_model=ResponseSchema[UserMcpInstallBulkUpdateResponse])
async def bulk_update_user_mcp_installs(
    request: UserMcpInstallBulkUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.bulk_update_installs(db, actor.user_id, request)
    return Response.success(data=result, message="MCP installs updated")


@router.patch("/{install_id}", response_model=ResponseSchema[UserMcpInstallResponse])
async def update_user_mcp_install(
    install_id: int,
    request: UserMcpInstallUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update_install(db, actor.user_id, install_id, request)
    return Response.success(data=result, message="MCP install updated")


@router.delete("/{install_id}", response_model=ResponseSchema[dict])
async def delete_user_mcp_install(
    install_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service.delete_install(db, actor.user_id, install_id)
    return Response.success(data={"id": install_id}, message="MCP install deleted")
